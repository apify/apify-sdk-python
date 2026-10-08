from __future__ import annotations

import asyncio
from logging import getLogger
from typing import TYPE_CHECKING, Self
from weakref import WeakValueDictionary

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
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


class ChildRunRecord(BaseModel):
    """A child run tracked under a name in the child run registry."""

    model_config = ConfigDict(populate_by_name=True, alias_generator=to_camel)

    actor_id: str | None = None
    """The Actor ID or name the child was started with, as the caller passed it, or `None` for a task run."""

    task_id: str | None = None
    """The task ID or name the child was started with, as the caller passed it, or `None` for an Actor run."""

    run_id: str
    """ID of the current run under this name."""

    previous_run_ids: list[str] = Field(default_factory=list)
    """IDs of earlier runs under this name that failed and were replaced by a new run, oldest first."""

    @model_validator(mode='after')
    def _check_started_from(self) -> Self:
        if (self.actor_id is None) == (self.task_id is None):
            raise ValueError('Exactly one of `actor_id` and `task_id` must be set.')
        return self


def _describe_started_from(actor_id: str | None, task_id: str | None) -> str:
    return f'Actor "{actor_id}"' if actor_id is not None else f'task "{task_id}"'


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
            actor_id: The Actor to start. It must match the Actor already recorded under `name`.
            task_id: The task to start, in place of `actor_id`. It must match the task already recorded under `name`.
            client: Client used to look up the recorded run.
            start_run: Starts a new run of the Actor or task.
            resurrect_run: Resurrects the recorded run, given its ID.

        Returns:
            The run, and whether it was newly started.
        """
        async with self._name_locks.setdefault(name, asyncio.Lock()):
            records = await self._load()
            record = records.get(name)

            if record is None:
                run = await self._start(
                    name, actor_id=actor_id, task_id=task_id, start_run=start_run, previous_run_ids=[]
                )
                return run, True

            if (record.actor_id, record.task_id) != (actor_id, task_id):
                raise ValueError(
                    f'Child run "{name}" is already recorded for '
                    f'{_describe_started_from(record.actor_id, record.task_id)}, '
                    f'it cannot be reused for {_describe_started_from(actor_id, task_id)}.'
                )

            run_client = client.run(record.run_id)
            run = await _get_recorded_run(run_client)

            if run is not None and run.status in _SETTLING_STATUSES:
                run = await run_client.wait_for_finish()

            if run is None or run.status == 'FAILED':
                previous_run_ids = [*record.previous_run_ids, record.run_id]
                run = await self._start(
                    name, actor_id=actor_id, task_id=task_id, start_run=start_run, previous_run_ids=previous_run_ids
                )
                return run, True

            if run.status in _RESURRECTABLE_STATUSES:
                logger.info(f'Resurrecting child run "{name}"', extra={'run_id': run.id, 'status': run.status})
                return await resurrect_run(run.id), False

            logger.info(f'Reattaching to child run "{name}"', extra={'run_id': run.id, 'status': run.status})
            return run, False

    async def _start(
        self,
        name: str,
        *,
        actor_id: str | None,
        task_id: str | None,
        start_run: Callable[[], Awaitable[Run]],
        previous_run_ids: list[str],
    ) -> Run:
        run = await start_run()
        record = ChildRunRecord(actor_id=actor_id, task_id=task_id, run_id=run.id, previous_run_ids=previous_run_ids)
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
