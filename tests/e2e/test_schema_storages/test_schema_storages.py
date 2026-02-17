from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..conftest import MakeActorFunction, RunActorFunction

_ACTOR_SOURCE_DIR = Path(__file__).parent / 'actor_source'


def read_actor_source(filename: str) -> str:
    return (_ACTOR_SOURCE_DIR / filename).read_text()


async def test_configuration_storages(make_actor: MakeActorFunction, run_actor: RunActorFunction) -> None:
    actor = await make_actor(
        label='schema_storages',
        source_files={
            'src/main.py': read_actor_source('main.py'),
            '.actor/actor.json': read_actor_source('actor.json'),
        },
    )
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'
