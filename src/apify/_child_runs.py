from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime
from logging import getLogger
from typing import TYPE_CHECKING, Any
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from pydantic.alias_generators import to_camel

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

_NOT_FOUND_GRACE_SECS = 3
"""How long a recorded run that the API reports as missing is looked up again before it counts as gone."""

_NOT_FOUND_RETRY_INTERVAL_SECS = 0.25


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
    """The current run tracked under a name in the child run registry, with the runs it replaced."""

    checksum: str
    """Hash of the Actor or task and the input the name was first used with."""

    history: list[ChildRunSnapshot] = Field(default_factory=list)
    """Earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""


def checksum_request(*, actor_id: str | None, task_id: str | None, run_input: Any) -> str:
    """Hash the Actor or task and the input of a named start, in the same JSON shape as the JS SDK."""
    request: dict[str, Any] = (
        {'type': 'actor', 'id': actor_id} if actor_id is not None else {'type': 'task', 'id': task_id}
    )
    if run_input is not None:
        request['input'] = run_input
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
    """Persisted name -> run map that lets named child runs survive a migration or resurrection of the parent.

    Every change is written to the key-value store right away. A hard kill of the parent between the platform
    starting the child and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(self, open_key_value_store: Callable[[], Awaitable[KeyValueStore]]) -> None:
        self._open_key_value_store = open_key_value_store
        self._records: dict[str, ChildRunRecord] | None = None
        self._lock = asyncio.Lock()
        """Guards loading the records and writing them back to the key-value store."""
        self._name_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        """Serializes `find_or_start` per name. A lock is dropped once no call under its name holds it."""

    async def find_or_start(
        self,
        name: str,
        *,
        actor_id: str | None = None,
        task_id: str | None = None,
        run_input: Any,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        resurrect_run: Callable[[str], Awaitable[Run]],
    ) -> tuple[Run, bool]:
        """Return the run recorded under `name`, or start one when there is none to reuse.

        A recorded run that is `READY` or `RUNNING` is reattached and one that `SUCCEEDED` is returned as is.
        An `ABORTED` or `TIMED-OUT` run is resurrected, since Actors are expected to resume from their state.
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name.

        Args:
            name: Name of the child run, unique within the parent run.
            actor_id: The Actor to start.
            task_id: The task to start, in place of `actor_id`.
            run_input: Input of the run. With the Actor or task, it must match what `name` was first used with.
            client: Client used to look up the recorded run.
            start_run: Starts a new run of the Actor or task.
            resurrect_run: Resurrects the recorded run, given its ID.

        Returns:
            The run, and whether it was newly started.
        """
        checksum = checksum_request(actor_id=actor_id, task_id=task_id, run_input=run_input)

        async with self._name_locks.setdefault(name, asyncio.Lock()):
            records = await self._load()
            record = records.get(name)

            if record is None:
                run = await self._start(name, checksum=checksum, start_run=start_run, history=[])
                return run, True

            if record.checksum != checksum:
                raise ValueError(
                    f'The run name "{name}" was already used for a different Actor, task or input. '
                    'Use a unique `run_name` for each child run.'
                )

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
                    name, checksum=checksum, start_run=start_run, history=[*record.history, replaced]
                )
                return run, True

            if run.status in _RESURRECTABLE_STATUSES:
                logger.info(f'Resurrecting child run "{name}"', extra={'run_id': run.id, 'status': run.status})
                run = await resurrect_run(run.id)
            else:
                logger.info(f'Reattaching to child run "{name}"', extra={'run_id': run.id, 'status': run.status})

            await self.update(name, run)
            return run, False

    async def update(self, name: str, run: Run) -> None:
        """Record the latest observed status of the run recorded under `name`.

        Args:
            name: Name of the child run.
            run: The run as just returned by the API. Nothing is recorded unless it is the current run under `name`.
        """
        record = (await self._load()).get(name)
        if record is None or record.run_id != run.id or record.status == run.status:
            return
        await self._save(name, record.model_copy(update={'status': run.status}))

    async def _start(
        self,
        name: str,
        *,
        checksum: str,
        start_run: Callable[[], Awaitable[Run]],
        history: list[ChildRunSnapshot],
    ) -> Run:
        run = await start_run()
        record = ChildRunRecord(
            run_id=run.id, status=run.status, started_at=run.started_at, checksum=checksum, history=history
        )
        await self._save(name, record)
        return run

    async def _load(self) -> dict[str, ChildRunRecord]:
        async with self._lock:
            if self._records is None:
                key_value_store = await self._open_key_value_store()
                stored = await key_value_store.get_value(CHILD_RUNS_KEY)
                try:
                    self._records = _records_adapter.validate_python(stored or {})
                except ValidationError as exc:
                    raise ValueError(
                        f'The child run registry under the "{CHILD_RUNS_KEY}" key in the default key-value store '
                        'is malformed.'
                    ) from exc
            return self._records

    async def _save(self, name: str, record: ChildRunRecord) -> None:
        records = await self._load()
        key_value_store = await self._open_key_value_store()
        async with self._lock:
            records[name] = record
            await key_value_store.set_value(
                CHILD_RUNS_KEY, _records_adapter.dump_python(records, by_alias=True, mode='json')
            )
