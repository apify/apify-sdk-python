from __future__ import annotations

import asyncio
import hashlib
import json
from abc import ABC, abstractmethod
from logging import getLogger
from typing import TYPE_CHECKING, Any, NamedTuple
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel

from apify_client.errors import NotFoundError
from apify_client.http_clients import StreamedRequestBody

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from apify_client import ApifyClientAsync
    from apify_client._literals import ActorPermissionLevel
    from apify_client._models import Run, WebhookRepresentation
    from apify_client._resource_clients import RunClientAsync

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = 'APIFY_ACTOR_CHILD_RUNS'
"""Key in the default key-value store under which the child run registry is persisted."""

_ABORTED_STATUSES = frozenset({'ABORTING', 'ABORTED'})

TERMINAL_RUN_STATUSES = frozenset({'SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'})
"""Statuses of a run that is finished. A run in any other status is active."""

_NOT_FOUND_GRACE_SECS = 3
"""How long a recorded run that the API reports as missing is looked up again before it counts as gone."""

_NOT_FOUND_RETRY_INTERVAL_SECS = 0.25

EXCESSIVE_CHILD_RUNS_THRESHOLD = 50
"""Number of records above which the registry logs a warning about its size, once per process."""


def run_key(run_id: str) -> str:
    """Return the registry key of a child run started without a run name."""
    return f'run:{run_id}'


def name_key(run_name: str) -> str:
    """Return the registry key of a child run started with `run_name`."""
    return f'name:{run_name}'


def implicit_key(checksum: str) -> str:
    """Return the registry key of a child run whose implicit run name is the checksum of its request."""
    return f'implicit:{checksum}'


@docs_group('Actor')
class ChildRunRecord(BaseModel):
    """A child run as recorded in the child run registry of this Actor run.

    Fields this SDK version does not know, e.g. written by a newer SDK before a metamorph, are kept.
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel, frozen=True, extra='allow')

    run_id: str
    """ID of the run."""

    status: str
    """Last status of the run observed by this Actor run. It can be out of date."""

    abort_with_parent: bool = False
    """Whether the run is aborted when this Actor run is gracefully aborted."""

    checksum: str | None = None
    """SHA-256 of the request a named run was started with. `None` for a run started without a run name."""


@docs_group('Actor')
class ChildRun(NamedTuple):
    """A child run of this Actor run, as listed in `Actor.child_runs`."""

    key: str
    """Key of the run in the child run registry, such as `run:<run ID>` or `name:<run name>`."""

    record: ChildRunRecord
    """Read-only copy of the record stored in the child run registry."""

    client: RunClientAsync
    """Client for the run."""


@docs_group('Actor')
class ChildRunTracker(ABC):
    """Storage of the child run registry of an Actor run.

    The Actor reads the records once, when it starts, and stores a record every time it changes. The default tracker
    keeps the registry in the default key-value store under the `APIFY_ACTOR_CHILD_RUNS` key. A custom tracker, passed
    as `Actor(child_run_tracker=...)`, can store the records elsewhere or encrypt them.
    """

    @abstractmethod
    async def list_runs(self) -> dict[str, ChildRunRecord]:
        """Return the stored records by their key, in the order in which they were first stored.

        Raises:
            ValueError: If the stored registry is malformed.
        """

    @abstractmethod
    async def store_run(self, key: str, record: ChildRunRecord) -> None:
        """Store `record` under `key`, replacing the record stored under it.

        Args:
            key: Key of the record, such as `run:<run ID>` or `name:<run name>`.
            record: The record to store.
        """


class _StoredRegistry(BaseModel):
    """The child run registry as stored in the default key-value store.

    Top-level members this SDK version does not know are kept.
    """

    model_config = ConfigDict(extra='allow')

    runs: dict[str, ChildRunRecord] = Field(default_factory=dict)


class KeyValueStoreChildRunTracker(ChildRunTracker):
    """Child run tracker that keeps the registry in the default key-value store of the Actor run."""

    def __init__(self, open_key_value_store: Callable[[], Awaitable[KeyValueStore]]) -> None:
        self._open_key_value_store = open_key_value_store
        self._stored = _StoredRegistry()

    async def list_runs(self) -> dict[str, ChildRunRecord]:
        key_value_store = await self._open_key_value_store()
        stored = await key_value_store.get_value(CHILD_RUNS_KEY)
        try:
            self._stored = _StoredRegistry.model_validate({} if stored is None else stored)
        except ValidationError as exc:
            raise ValueError(
                f'The child run registry under the "{CHILD_RUNS_KEY}" key in the default key-value store is malformed.'
            ) from exc
        return dict(self._stored.runs)

    async def store_run(self, key: str, record: ChildRunRecord) -> None:
        self._stored.runs[key] = record
        key_value_store = await self._open_key_value_store()
        await key_value_store.set_value(
            CHILD_RUNS_KEY, self._stored.model_dump(mode='json', by_alias=True, exclude_none=True)
        )


def _canonical_number(value: float) -> str:
    """Serialize a finite float the way `Number.prototype.toString` of ECMAScript does, as RFC 8785 requires."""
    if value == 0:
        return '0'

    sign = '-' if value < 0 else ''
    mantissa, _, exponent = repr(abs(value)).partition('e')
    integer_part, _, fraction_part = mantissa.partition('.')

    # The value equals `0.<digits> * 10 ** point`.
    all_digits = integer_part + fraction_part
    significant_digits = all_digits.lstrip('0')
    point = len(integer_part) + int(exponent or 0) - (len(all_digits) - len(significant_digits))
    digits = significant_digits.rstrip('0')
    digit_count = len(digits)

    if digit_count <= point <= 21:  # noqa: PLR2004
        return f'{sign}{digits}{"0" * (point - digit_count)}'
    if 0 < point <= 21:  # noqa: PLR2004
        return f'{sign}{digits[:point]}.{digits[point:]}'
    if -6 < point <= 0:  # noqa: PLR2004
        return f'{sign}0.{"0" * -point}{digits}'

    exponent_sign = '+' if point > 0 else '-'
    fraction = f'.{digits[1:]}' if digit_count > 1 else ''
    return f'{sign}{digits[0]}{fraction}e{exponent_sign}{abs(point - 1)}'


def _canonical_json(value: Any) -> str:
    """Serialize a JSON value as canonical JSON (RFC 8785, JCS).

    An integer too large for an IEEE 754 double is written with all its digits, since that is what the client sends.
    """
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _canonical_number(value)
    if isinstance(value, (list, tuple)):
        items = ','.join(_canonical_json(item) for item in value)
        return f'[{items}]'
    if isinstance(value, dict):
        # RFC 8785 sorts the keys by their UTF-16 code units.
        sorted_keys = sorted(value, key=lambda key: key.encode('utf-16-be', 'surrogatepass'))
        members = [f'{json.dumps(key, ensure_ascii=False)}:{_canonical_json(value[key])}' for key in sorted_keys]
        return f'{{{",".join(members)}}}'
    raise TypeError(f'Cannot serialize a {type(value).__name__} value as canonical JSON.')


def _to_json_input(run_input: Any, content_type: str | None) -> Any:
    """Convert the input of a run to the JSON document the client sends to the API.

    Raises:
        TypeError: If the client would not send the input as JSON.
    """
    if content_type and 'application/json' not in content_type.lower():
        raise TypeError(f'the content type of the input is {content_type!r}')
    if isinstance(run_input, (str, bytes, bytearray)) or StreamedRequestBody.is_streamable(run_input):
        raise TypeError(f'the input is a {type(run_input).__name__}')
    serialized = json.dumps(run_input, ensure_ascii=False, allow_nan=False, default=str)
    return json.loads(serialized)


def checksum_run_options(
    *,
    build: str | None = None,
    force_permission_level: ActorPermissionLevel | None = None,
    webhooks: list[WebhookRepresentation] | None = None,
) -> dict[str, Any]:
    """Return the run options that enter the checksum and are set, under the names and with the values of the API.

    Only the options that change which code runs, or what it is allowed to do, enter the checksum. The others, such
    as the memory limit or the timeout, can differ between processes of this Actor run.

    Args:
        build: The Actor build to run.
        force_permission_level: Permission level of the run.
        webhooks: Ad-hoc webhooks of the run.
    """
    webhook_dicts = [webhook.model_dump(mode='json', by_alias=True, exclude_none=True) for webhook in webhooks or []]
    options = {
        'build': build,
        'forcePermissionLevel': force_permission_level,
        'webhooks': webhook_dicts or None,
    }
    return {name: value for name, value in options.items() if value is not None}


def checksum_request(
    *,
    actor_id: str | None = None,
    task_id: str | None = None,
    run_input: Any = None,
    content_type: str | None = None,
    options: dict[str, Any] | None = None,
    run_name: str | None = None,
    require_json_input: bool = False,
) -> str:
    """Hash the Actor or task, the input, and the run options of a start, in the same JSON shape as the JS SDK.

    An input that the client would not send as JSON is left out, and a warning says that it was not checked.

    Args:
        actor_id: The Actor to start.
        task_id: The task to start, in place of `actor_id`.
        run_input: Input of the run.
        content_type: Content type of the input.
        options: Run options from `checksum_run_options`.
        run_name: Run name of the call, used in the warning about an input that is not JSON.
        require_json_input: Whether an input that is not JSON raises instead. An implicit run name needs the input,
            since without it calls with different inputs would get the same name.

    Raises:
        TypeError: If `require_json_input` is set and the client would not send the input as JSON.
    """
    request: dict[str, Any] = (
        {'type': 'actor', 'id': actor_id} if actor_id is not None else {'type': 'task', 'id': task_id}
    )
    try:
        json_input = _to_json_input(run_input, content_type)
    except TypeError as exc:
        if require_json_input:
            raise TypeError(
                f'An implicit run name needs a JSON input, but {exc}. Pass a `run_name`, or turn '
                '`Configuration.auto_memoize_child_runs` off.'
            ) from exc
        logger.warning(
            'The input of child run "%s" is not JSON (%s), so it was not checked against the recorded run',
            run_name,
            exc,
        )
        json_input = None
    if json_input is not None:
        request['input'] = json_input
    if options:
        request['options'] = options
    serialized = _canonical_json(request)
    return hashlib.sha256(serialized.encode('utf-8', 'surrogatepass')).hexdigest()


async def _get_recorded_run(run_client: RunClientAsync) -> Run | None:
    """Fetch a recorded run, retrying a 404 for a few seconds.

    A run started moments ago, e.g. by a concurrent call under the same key, may not be on every API replica yet,
    and treating it as gone would start a duplicate.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _NOT_FOUND_GRACE_SECS
    while True:
        run = await run_client.get()
        if run is not None or loop.time() >= deadline:
            return run
        await asyncio.sleep(_NOT_FOUND_RETRY_INTERVAL_SECS)


class ChildRunRegistry:
    """Records every child run of this Actor run, so that a migration, reboot, or resurrection of it keeps them.

    Every change is stored by the tracker right away. A hard kill of the parent between the platform starting the child
    and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(self, tracker: ChildRunTracker | None, *, warn_on_excessive_runs: bool = True) -> None:
        """Initialize a new instance.

        Args:
            tracker: Storage of the records, or `None` to turn child run tracking off.
            warn_on_excessive_runs: Whether to log a warning once the registry holds too many records.
        """
        self._tracker = tracker
        self._warn_on_excessive_runs = warn_on_excessive_runs
        self._records: dict[str, ChildRunRecord] | None = None
        self._loaded = asyncio.Event()
        """Set once the Actor has read the records from the tracker, or has failed to."""
        self._lock = asyncio.Lock()
        """Guards loading the records and storing them through the tracker."""
        self._key_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        """Serializes `find_or_start` per key. A lock is dropped once no call under its key holds it."""
        self._clients: dict[str, ApifyClientAsync] = {}
        """Client the run under each key was last started or looked up with. Lost with the process."""
        self._parent_aborting = False
        """Whether this Actor run is being gracefully aborted, after which no run marked `abort_with_parent` starts."""
        self._warned_excessive_runs = False

    @property
    def is_enabled(self) -> bool:
        """Whether child run tracking is on."""
        return self._tracker is not None

    async def find_or_start(
        self,
        key: str,
        *,
        checksum: str,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        abort_with_parent: bool = False,
    ) -> tuple[Run, bool]:
        """Return the run recorded under `key`, or start one when there is none.

        A recorded run is returned in whatever status it is in. Only a recorded run that the API no longer knows is
        replaced by a new run under the same key.

        Args:
            key: Key of the child run, unique within the parent run.
            checksum: Hash of the request from `checksum_request`. The recorded run is returned only if it was
                started with the same request.
            client: Client used to look up the recorded run.
            start_run: Starts a new run of the Actor or task.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted. It replaces the value
                recorded under `key`.

        Returns:
            The run, and whether it was newly started.

        Raises:
            ValueError: If the run recorded under `key` was started with a different request.
            RuntimeError: If `abort_with_parent` is set and this Actor run is being gracefully aborted. No run is
                started or returned.
        """
        async with self._key_locks.setdefault(key, asyncio.Lock()):
            if abort_with_parent and self._parent_aborting:
                raise RuntimeError(
                    f'Child run "{key}" with `abort_with_parent` was not started, since this Actor run is being '
                    'aborted.'
                )

            record = self._get_records().get(key)

            if record is not None:
                if record.checksum != checksum:
                    raise ValueError(
                        f'The run name of child run "{key}" was already used for a different Actor, task, input or '
                        'run options. Use a unique `run_name` for each child run.'
                    )

                run = await _get_recorded_run(client.run(record.run_id))

                if run is not None:
                    logger.info('Reattaching to child run "%s"', key, extra={'run_id': run.id, 'status': run.status})
                    updated_record = record.model_copy(
                        update={'status': run.status, 'abort_with_parent': abort_with_parent}
                    )
                    if updated_record != record:
                        await self._store(key, updated_record)
                    self._clients[key] = client
                    return run, False

                logger.warning(
                    'Child run "%s" no longer exists, starting a new run in its place',
                    key,
                    extra={'run_id': record.run_id},
                )

            run = await start_run()
            new_record = ChildRunRecord(
                run_id=run.id,
                status=run.status,
                abort_with_parent=abort_with_parent,
                checksum=checksum,
            )
            await self._store(key, new_record)
            self._clients[key] = client
            return run, True

    async def record(self, run: Run, *, client: ApifyClientAsync) -> str:
        """Record a run started without a run name.

        Args:
            run: The run as returned by the start request.
            client: Client the run was started with.

        Returns:
            Key of the run in the registry.
        """
        key = run_key(run.id)
        await self._store(key, ChildRunRecord(run_id=run.id, status=run.status))
        self._clients[key] = client
        return key

    def child_runs(self, default_client: ApifyClientAsync) -> list[ChildRun]:
        """Return the key, the record and a client of every recorded run, in recording order.

        Each client comes from the client its key was last started or looked up with in this process, so a run started
        with a custom token uses that token.

        Args:
            default_client: Client used for a key not started or looked up in this process, e.g. one recorded by
                an earlier process of this Actor run.
        """
        child_runs: list[ChildRun] = []
        for key, record in self._get_records().items():
            client = self._clients.get(key, default_client)
            child_runs.append(ChildRun(key=key, record=record, client=client.run(record.run_id)))
        return child_runs

    async def update(self, key: str, run: Run) -> None:
        """Record the latest observed status of the run recorded under `key`.

        Args:
            key: Key of the child run.
            run: The run as just returned by the API. Nothing is recorded unless it is the run under `key`.
        """
        record = self._get_records().get(key)
        if record is None or record.run_id != run.id or record.status == run.status:
            return
        await self._store(key, record.model_copy(update={'status': run.status}))

    async def abort_runs_with_parent(self, client: ApifyClientAsync) -> None:
        """Gracefully abort every recorded run marked `abort_with_parent`, and refuse to start any more of them.

        Each run gets one abort request, all in parallel. The platform leaves a run that already finished as it is. A
        failure to abort one run is logged and does not stop the others. A run whose start is in flight is aborted once
        the start records it.

        Args:
            client: Client used for a key not started or looked up in this process, e.g. one recorded by an earlier
                process of this Actor run.
        """
        self._parent_aborting = True
        # The event can arrive before the Actor has loaded the registry.
        await self._loaded.wait()
        # The Actor failed to load the registry, so it knows no runs to abort.
        if self._records is None:
            return
        # Keys with a start in flight are not recorded yet, so their locks are awaited too.
        await asyncio.gather(*(self._abort(key, client) for key in {*self._records, *self._key_locks}))

    async def _abort(self, key: str, default_client: ApifyClientAsync) -> None:
        async with self._key_locks.setdefault(key, asyncio.Lock()):
            record = self._get_records().get(key)
            if record is None or not record.abort_with_parent:
                return
            run_client = self._clients.get(key, default_client).run(record.run_id)
            try:
                run = await run_client.abort(gracefully=True)
            except NotFoundError:
                logger.debug('Child run "%s" no longer exists', key, extra={'run_id': record.run_id})
            except Exception:
                logger.exception('Failed to abort child run "%s"', key, extra={'run_id': record.run_id})
            else:
                if run.status in _ABORTED_STATUSES:
                    logger.info('Aborted child run "%s" with the parent', key, extra={'run_id': record.run_id})

    async def load(self) -> None:
        """Read the records through the tracker, replacing any read before. Does nothing with tracking off."""
        async with self._lock:
            try:
                if self._tracker is not None:
                    self._records = await self._tracker.list_runs()
                    self._warn_if_excessive()
            finally:
                self._loaded.set()

    def stop_waiting_for_load(self) -> None:
        """Release an abort of the child runs that waits for the registry, when the Actor fails before it loads it."""
        self._loaded.set()

    def _get_records(self) -> dict[str, ChildRunRecord]:
        if self._records is None:
            raise RuntimeError('The child run registry is not loaded.')
        return self._records

    async def _store(self, key: str, record: ChildRunRecord) -> None:
        records = self._get_records()
        if self._tracker is None:
            raise RuntimeError('Child run tracking is turned off.')
        async with self._lock:
            records[key] = record
            self._warn_if_excessive()
            await self._tracker.store_run(key, record)

    def _warn_if_excessive(self) -> None:
        if (
            not self._warn_on_excessive_runs
            or self._warned_excessive_runs
            or len(self._get_records()) <= EXCESSIVE_CHILD_RUNS_THRESHOLD
        ):
            return
        self._warned_excessive_runs = True
        logger.warning(
            'Too many child runs (%d). Tracking them can cause performance issues and excessive key-value store '
            'usage. Turn child run tracking off with `Actor(child_run_tracker=None)`, or mute this warning with '
            '`Actor(disable_excessive_child_run_warning=True)`.',
            len(self._get_records()),
        )
