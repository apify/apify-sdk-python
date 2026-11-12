from __future__ import annotations

import asyncio
import hashlib
import json
from collections import Counter
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.alias_generators import to_camel

from apify_client.errors import NotFoundError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import RunClientAsync

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = '__ACTOR_CHILD_RUNS'
"""Key in the default key-value store under which the child run registry is persisted."""

_SETTLING_STATUSES = frozenset({'ABORTING', 'TIMING-OUT'})
"""Statuses that end as `ABORTED` / `TIMED-OUT` shortly, and are resurrectable once they do."""

_RESURRECTABLE_STATUSES = frozenset({'ABORTED', 'TIMED-OUT'})

_ABORTED_STATUSES = frozenset({'ABORTING', 'ABORTED'})

_NOT_FOUND_GRACE_SECS = 3
"""How long a recorded run that the API reports as missing is looked up again before it counts as gone."""

_NOT_FOUND_RETRY_INTERVAL_SECS = 0.25

_IMPLICIT_KEY_HASH_LENGTH = 16
"""Number of hex digits of the request hash kept in the key of a child run started without a name."""


class ChildRunSnapshot(BaseModel):
    """A child run as last observed by this Actor run."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    run_id: str
    """ID of the run."""

    status: str
    """Last status of the run observed by this Actor run, or `LOST` once the platform no longer returned it."""

    started_at: datetime
    """When the run started."""


class ChildRunRecord(ChildRunSnapshot):
    """The current run tracked under a name or implicit key in the child run registry, with the runs it replaced."""

    run_name: str | None = None
    """Name the run was started under, or `None` for a run started without a name."""

    checksum: str
    """Hash of the Actor or task and the input the current run was started with."""

    history: list[ChildRunSnapshot] = Field(default_factory=list)
    """Earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""

    abort_with_parent: bool = False
    """Whether the current run is aborted when this Actor run is gracefully aborted."""


def checksum_request(
    *, actor_id: str | None, task_id: str | None, run_input: Any, run_options: dict[str, Any] | None = None
) -> str:
    """Hash the Actor or task, the input and the run options of a start.

    Without run options, the hashed JSON has the same shape as in the JS SDK. Only the options set to anything but
    `None` are hashed, so a run option added to the SDK later does not change the hash of a start that does not use it.
    """
    request: dict[str, Any] = (
        {'type': 'actor', 'id': actor_id} if actor_id is not None else {'type': 'task', 'id': task_id}
    )
    if run_input is not None:
        request['input'] = run_input
    options = {name: value for name, value in (run_options or {}).items() if value is not None}
    if options:
        request['options'] = options
    serialized = json.dumps(request, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def _get_recorded_run(run_client: RunClientAsync) -> Run | None:
    """Fetch a recorded run, retrying a 404 for a few seconds.

    A run started moments ago, e.g. by a concurrent call under the same name, may not be on every API replica yet,
    and treating it as gone would start a duplicate.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _NOT_FOUND_GRACE_SECS
    while True:
        run = await run_client.get()
        if run is not None or loop.time() >= deadline:
            return run
        await asyncio.sleep(_NOT_FOUND_RETRY_INTERVAL_SECS)


_records_adapter = TypeAdapter(dict[str, ChildRunRecord])


class ChildRunRegistry:
    """Persisted record of the child runs of this Actor run, which survives a migration or resurrection of the parent.

    A named child run is recorded under its name, so a later start under the same name can reattach to it. A child run
    started without a name is recorded under an implicit key: a hash of its Actor or task, input and run options, and
    the number of identical starts without a name before it in this process, as in `3f2a9c0e1b7d4a65-0`. After a
    migration, the starts run again in the same order, so the n-th identical start reattaches to the n-th recorded run.
    Every change is written to the key-value store right away. A hard kill of the parent between the platform starting
    the child and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(self, open_key_value_store: Callable[[], Awaitable[KeyValueStore]]) -> None:
        self._open_key_value_store = open_key_value_store
        self._key_value_store: KeyValueStore | None = None
        """The default key-value store the records were loaded from, which every change is written to."""
        self._records: dict[str, ChildRunRecord] | None = None
        """Records of the child runs by name, or by implicit key for a run started without a name.

        `None` until loaded.
        """
        self._lock = asyncio.Lock()
        """Guards loading the records and writing them back to the key-value store."""
        self._name_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        """Serializes `find_or_start` per key. A lock is dropped once no call under its key holds it."""
        self._clients: dict[str, ApifyClientAsync] = {}
        """Client the run under each key was last started or looked up with. Lost on a migration."""
        self._implicit_starts: Counter[str] = Counter()
        """Number of starts without a name in this process, by the hash part of their implicit key."""
        self._parent_aborting = False
        """Whether this Actor run is being gracefully aborted, after which no run marked `abort_with_parent` starts."""

    async def find_or_start(
        self,
        name: str | None,
        *,
        actor_id: str | None = None,
        task_id: str | None = None,
        run_input: Any,
        run_options: dict[str, Any] | None = None,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        resurrect_run: Callable[[str], Awaitable[Run]],
        abort_with_parent: bool = False,
    ) -> tuple[Run, bool]:
        """Return the run recorded under `name` or the implicit key, or start one when there is none to reuse.

        A recorded run that is `READY` or `RUNNING` is reattached and one that `SUCCEEDED` is returned as is.
        An `ABORTED` or `TIMED-OUT` run is resurrected, since Actors are expected to resume from their state.
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name, for any Actor,
        task or input.

        Args:
            name: Name of the child run, unique within the parent run, or `None` to use the implicit key.
            actor_id: The Actor to start.
            task_id: The task to start, in place of `actor_id`.
            run_input: Input of the run. The recorded run is reused only if it was started with the same Actor or task
                and input.
            run_options: Options the run is started with. Without `name`, they are part of the implicit key.
            client: Client used to look up the recorded run.
            start_run: Starts a new run of the Actor or task.
            resurrect_run: Resurrects the recorded run, given its ID.
            abort_with_parent: Whether to abort the run when this Actor run is gracefully aborted. It replaces the
                recorded value.

        Returns:
            The run, and whether it was newly started.

        Raises:
            ValueError: If the recorded run would be reused, but was started for a different Actor, task or input.
            RuntimeError: If `abort_with_parent` is set and this Actor run is being gracefully aborted. No run is
                started, resurrected or reattached.
        """
        checksum = checksum_request(actor_id=actor_id, task_id=task_id, run_input=run_input)
        key = name
        if key is None:
            request_hash = checksum_request(
                actor_id=actor_id, task_id=task_id, run_input=run_input, run_options=run_options
            )[:_IMPLICIT_KEY_HASH_LENGTH]
            key = f'{request_hash}-{self._implicit_starts[request_hash]}'
            self._implicit_starts[request_hash] += 1

        async with self._name_locks.setdefault(key, asyncio.Lock()):
            if abort_with_parent and self._parent_aborting:
                raise RuntimeError(
                    f'Child run "{key}" with `abort_with_parent` was not started, since this Actor run is being '
                    'aborted.'
                )

            records = await self._load()
            record = records.get(key)

            if record is None:
                run = await self._start(
                    key,
                    run_name=name,
                    checksum=checksum,
                    start_run=start_run,
                    history=[],
                    abort_with_parent=abort_with_parent,
                )
                self._clients[key] = client
                return run, True

            run_client = client.run(record.run_id)
            run = await _get_recorded_run(run_client)

            if run is not None and run.status in _SETTLING_STATUSES:
                run = await run_client.wait_for_finish()

            if run is None or run.status == 'FAILED':
                replaced = ChildRunSnapshot(
                    run_id=record.run_id,
                    status=run.status if run is not None else 'LOST',
                    started_at=record.started_at,
                )
                run = await self._start(
                    key,
                    run_name=name,
                    checksum=checksum,
                    start_run=start_run,
                    history=[*record.history, replaced],
                    abort_with_parent=abort_with_parent,
                )
                self._clients[key] = client
                return run, True

            if record.checksum != checksum:
                raise ValueError(
                    f'The run name "{key}" was already used for a different Actor, task or input. '
                    'Use a unique `run_name` for each child run.'
                )

            if record.abort_with_parent != abort_with_parent:
                await self._save(key, record.model_copy(update={'abort_with_parent': abort_with_parent}))

            if run.status in _RESURRECTABLE_STATUSES:
                logger.info('Resurrecting child run "%s"', key, extra={'run_id': run.id, 'status': run.status})
                run = await resurrect_run(run.id)
            else:
                logger.info('Reattaching to child run "%s"', key, extra={'run_id': run.id, 'status': run.status})

            await self._update(key, run)
            self._clients[key] = client
            return run, False

    def run_clients(self, default_client: ApifyClientAsync) -> dict[str, RunClientAsync]:
        """Return a client for the current run under each recorded key.

        A named run is keyed by its name, a run started without a name by its implicit key. Each client comes from the
        client its run was last started or looked up with in this process, so a run started with a custom token uses
        that token.

        Args:
            default_client: Client used for a run not started or looked up in this process, e.g. one recorded before a
                migration.
        """
        return {
            key: self._clients.get(key, default_client).run(record.run_id)
            for key, record in (self._records or {}).items()
        }

    async def update(self, run: Run) -> None:
        """Record the latest observed status of a run.

        Args:
            run: The run as just returned by the API. Nothing is recorded unless it is the current run under some key.
        """
        records = await self._load()
        key = next((key for key, record in records.items() if record.run_id == run.id), None)
        if key is not None:
            await self._update(key, run)

    async def _update(self, key: str, run: Run) -> None:
        record = (await self._load()).get(key)
        if record is None or record.run_id != run.id or record.status == run.status:
            return
        await self._save(key, record.model_copy(update={'status': run.status}))

    async def abort_runs_with_parent(self, client: ApifyClientAsync) -> None:
        """Gracefully abort every recorded run marked `abort_with_parent`, and refuse to start any more of them.

        Each run gets one abort request, all in parallel. The platform leaves a run that already finished as it is. A
        failure to abort one run is logged and does not stop the others. A run whose start is in flight is aborted once
        the start records it.

        Args:
            client: Client used for a run not started or looked up in this process, e.g. after a migration.
        """
        self._parent_aborting = True
        records = await self._load()
        # Keys with a start in flight are not recorded yet, so their locks are awaited too.
        await asyncio.gather(*(self._abort(key, client) for key in {*records, *self._name_locks}))

    async def _abort(self, key: str, default_client: ApifyClientAsync) -> None:
        async with self._name_locks.setdefault(key, asyncio.Lock()):
            record = (await self._load()).get(key)
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

    async def _start(
        self,
        key: str,
        *,
        run_name: str | None,
        checksum: str,
        start_run: Callable[[], Awaitable[Run]],
        history: list[ChildRunSnapshot],
        abort_with_parent: bool,
    ) -> Run:
        run = await start_run()
        record = ChildRunRecord(
            run_id=run.id,
            status=run.status,
            started_at=run.started_at,
            run_name=run_name,
            checksum=checksum,
            history=history,
            abort_with_parent=abort_with_parent,
        )
        await self._save(key, record)
        return run

    async def load(self) -> dict[str, ChildRunRecord]:
        """Read the records from the default key-value store, replacing any read before.

        The starts without a name are counted from zero again, since the code of this Actor run starts over after a
        migration or resurrection, and so do the implicit keys.
        """
        async with self._lock:
            self._implicit_starts.clear()
            key_value_store = await self._open_key_value_store()
            self._key_value_store = key_value_store
            stored = await key_value_store.get_value(CHILD_RUNS_KEY)
            try:
                self._records = _records_adapter.validate_python(stored or {})
            except ValidationError as exc:
                raise ValueError(
                    f'The child run registry under the "{CHILD_RUNS_KEY}" key in the default key-value store '
                    'is malformed.'
                ) from exc
            return self._records

    async def _load(self) -> dict[str, ChildRunRecord]:
        return self._records if self._records is not None else await self.load()

    def _loaded_key_value_store(self) -> KeyValueStore:
        if self._key_value_store is None:
            raise RuntimeError('The child run registry was not loaded.')
        return self._key_value_store

    async def _save(self, key: str, record: ChildRunRecord) -> None:
        records = await self._load()
        async with self._lock:
            records[key] = record
            await self._loaded_key_value_store().set_value(
                CHILD_RUNS_KEY, _records_adapter.dump_python(records, by_alias=True, mode='json')
            )
