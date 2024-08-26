from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import ActorFactory


class TestActorInit:
    async def test_actor_init(self: TestActorInit, make_actor: ActorFactory) -> None:
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

        actor = await make_actor('actor-init', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_async_with_actor_properly_initialize(self: TestActorInit, make_actor: ActorFactory) -> None:
        async def main() -> None:
            import apify.actor

            async with Actor:
                assert apify.actor.Actor._is_initialized
            assert apify.actor.Actor._is_initialized is False

        actor = await make_actor('with-actor-init', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'


class TestActorExit:
    async def test_actor_exit_code(self: TestActorExit, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                input = await Actor.get_input()  # noqa: A001
                await Actor.exit(**input)

        actor = await make_actor('actor-exit', main_func=main)

        for exit_code in [0, 1, 101]:
            run_result = await actor.call(run_input={'exit_code': exit_code})
            assert run_result is not None
            assert run_result['exitCode'] == exit_code
            assert run_result['status'] == 'FAILED' if exit_code > 0 else 'SUCCEEDED'


class TestActorFail:
    async def test_fail_exit_code(self: TestActorFail, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                input = await Actor.get_input()  # noqa: A001
                await Actor.fail(**input) if input else await Actor.fail()

        actor = await make_actor('actor-fail', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['exitCode'] == 1
        assert run_result['status'] == 'FAILED'

        for exit_code in [1, 10, 100]:
            run_result = await actor.call(run_input={'exit_code': exit_code})
            assert run_result is not None
            assert run_result['exitCode'] == exit_code
            assert run_result['status'] == 'FAILED'

        # fail with status message
        run_result = await actor.call(run_input={'status_message': 'This is a test message'})
        assert run_result is not None
        assert run_result['status'] == 'FAILED'
        assert run_result.get('statusMessage') == 'This is a test message'

    async def test_with_actor_fail_correctly(self: TestActorFail, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                raise Exception('This is a test exception')  # noqa: TRY002

        actor = await make_actor('with-actor-fail', main_func=main)
        run_result = await actor.call()
        assert run_result is not None
        assert run_result['exitCode'] == 91
        assert run_result['status'] == 'FAILED'
