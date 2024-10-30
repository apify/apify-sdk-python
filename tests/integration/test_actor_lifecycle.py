from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_actor_init_and_double_init_prevention(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        my_actor = Actor
        await my_actor.init()
        assert my_actor._is_initialized is True
        double_init = False
        try:
            await my_actor.init()
            double_init = True
        except RuntimeError as err:
            assert str(err) == 'The Actor was already initialized!'  # noqa: PT017
        except Exception:
            raise
        try:
            await Actor.init()
            double_init = True
        except RuntimeError as err:
            assert str(err) == 'The Actor was already initialized!'  # noqa: PT017
        except Exception:
            raise
        await my_actor.exit()
        assert double_init is False
        assert my_actor._is_initialized is False

    actor = await make_actor(label='actor-init', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_init_correctly_in_async_with_block(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        import apify._actor

        async with Actor:
            assert apify._actor.Actor._is_initialized
        assert apify._actor.Actor._is_initialized is False

    actor = await make_actor(label='with-actor-init', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_actor_exit_with_different_exit_codes(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            input = await Actor.get_input()  # noqa: A001
            await Actor.exit(**input)

    actor = await make_actor(label='actor-exit', main_func=main)

    for exit_code in [0, 1, 101]:
        run_result = await run_actor(actor, run_input={'exit_code': exit_code})

        assert run_result.exit_code == exit_code
        assert run_result.status == 'FAILED' if exit_code > 0 else 'SUCCEEDED'


async def test_actor_fail_with_custom_exit_codes_and_status_messages(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            input = await Actor.get_input()  # noqa: A001
            await Actor.fail(**input) if input else await Actor.fail()

    actor = await make_actor(label='actor-fail', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.exit_code == 1
    assert run_result.status == 'FAILED'

    for exit_code in [1, 10, 100]:
        run_result = await run_actor(actor, run_input={'exit_code': exit_code})

        assert run_result.exit_code == exit_code
        assert run_result.status == 'FAILED'

    # Fail with a status message.
    run_result = await run_actor(actor, run_input={'status_message': 'This is a test message'})

    assert run_result.status == 'FAILED'
    assert run_result.status_message == 'This is a test message'


async def test_actor_fails_correctly_with_exception(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    async def main() -> None:
        async with Actor:
            raise Exception('This is a test exception')  # noqa: TRY002

    actor = await make_actor(label='with-actor-fail', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.exit_code == 91
    assert run_result.status == 'FAILED'
