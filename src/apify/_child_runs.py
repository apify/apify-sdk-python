from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from logging import getLogger
from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from pydantic.alias_generators import to_camel

from apify._utils import docs_group

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from apify_client import ApifyClientAsync
    from apify_client._models import Run
    from apify_client._resource_clients import RunClientAsync

    from apify.storages import KeyValueStore

logger = getLogger(__name__)

CHILD_RUNS_KEY = 'APIFY_CHILD_RUNS'
"""Key in the default key-value store under which the child run registry is persisted."""

_SETTLING_STATUSES = frozenset({'ABORTING', 'TIMING-OUT'})
"""Statuses that end as `ABORTED` / `TIMED-OUT` shortly, and are resurrectable once they do."""

_RESURRECTABLE_STATUSES = frozenset({'ABORTED', 'TIMED-OUT'})


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
    """IDs of earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""

    @model_validator(mode='after')
    def _check_started_from(self) -> Self:
        if (self.actor_id is None) == (self.task_id is None):
            raise ValueError('Exactly one of `actor_id` and `task_id` must be set.')
        return self


def _describe_started_from(actor_id: str | None, task_id: str | None) -> str:
    return f'Actor "{actor_id}"' if actor_id is not None else f'task "{task_id}"'


@docs_group('Actor')
@dataclass(frozen=True)
class ChildRunInfo:
    """A named child run of this Actor run, as returned by `Actor.child_runs`."""

    actor_id: str
    """The Actor ID or name the child was started with, as the caller passed it."""

    run_id: str
    """ID of the current run under this name."""

    run: Run | None
    """The current run as the API returns it now, or `None` when the platform no longer knows it."""

    previous_run_ids: list[str]
    """IDs of earlier runs under this name that failed or went missing and were replaced by a new run, oldest first."""


_records_adapter = TypeAdapter(dict[str, ChildRunRecord])


class ChildRunRegistry:
    """Persisted name -> run map that lets named child runs survive a migration or resurrection of the parent.

    Every change is written to the key-value store right away. A hard kill of the parent between the platform
    starting the child and that write can still orphan the child, since nothing but the platform knows about it.
    """

    def __init__(self, open_key_value_store: Callable[[], Awaitable[KeyValueStore]]) -> None:
        self._open_key_value_store = open_key_value_store
        self._records: dict[str, ChildRunRecord] | None = None
        self._load_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._name_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def find_or_start(
        self,
        name: str,
        *,
        actor_id: str | None = None,
        task_id: str | None = None,
        client: ApifyClientAsync,
        start_run: Callable[[], Awaitable[Run]],
        resurrect_run: Callable[[RunClientAsync], Awaitable[Run]],
    ) -> tuple[Run, bool]:
        """Return the run recorded under `name`, or start one when there is none to reuse.

        A recorded run that is `READY` or `RUNNING` is reattached and one that `SUCCEEDED` is returned as is.
        An `ABORTED` or `TIMED-OUT` run is resurrected, since Actors are expected to resume from their state.
        A `FAILED` run, or one the API no longer knows, is replaced by a new run under the same name.

        Args:
            name: Name of the child run, unique within the parent run.
            actor_id: The Actor to start. It must match the Actor already recorded under `name`.
            task_id: The task to start, in place of `actor_id`. It must match the task already recorded under `name`.
            client: Client used to look up and resurrect the recorded run.
            start_run: Starts a new run of the Actor or task.
            resurrect_run: Resurrects the recorded run, given its run client.

        Returns:
            The run, and whether it was newly started.
        """
        async with self._name_locks[name]:
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
            run = await run_client.get()

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
                return await resurrect_run(run_client), False

            logger.info(f'Reattaching to child run "{name}"', extra={'run_id': run.id, 'status': run.status})
            return run, False

    async def list_runs(self, client: ApifyClientAsync) -> dict[str, ChildRunInfo]:
        """Return every recorded child run by name, with its current state fetched from the API.

        Args:
            client: Client used to fetch the recorded runs.
        """
        # Copy the records, since a named start can add one while the runs are fetched.
        records = dict(await self._load())
        runs = await asyncio.gather(*(client.run(record.run_id).get() for record in records.values()))
        return {
            name: ChildRunInfo(
                actor_id=record.actor_id,
                run_id=record.run_id,
                run=run,
                previous_run_ids=list(record.previous_run_ids),
            )
            for (name, record), run in zip(records.items(), runs, strict=True)
        }

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
        async with self._load_lock:
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
        async with self._write_lock:
            records[name] = record
            await key_value_store.set_value(
                CHILD_RUNS_KEY, _records_adapter.dump_python(records, by_alias=True, mode='json')
            )
