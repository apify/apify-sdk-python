from apify import Actor

from .conftest import ActorFactory


class TestActorInit:

    async def test_actor_init(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            my_actor = Actor()
            await my_actor.init()
            assert my_actor._is_initialized is True
            double_init = False
            try:
                await my_actor.init()
                double_init = True
            except RuntimeError as err:
                assert str(err) == 'The actor was already initialized!'
            except Exception as err:
                raise err
            try:
                await Actor.init()
                double_init = True
            except RuntimeError as err:
                assert str(err) == 'The actor was already initialized!'
            except Exception as err:
                raise err
            await my_actor.exit()
            assert double_init is False
            assert my_actor._is_initialized is False

        actor = await make_actor('actor-init', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'

    async def test_async_with_actor_properly_initialize(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                assert Actor._get_default_instance()._is_initialized
            assert Actor._get_default_instance()._is_initialized is False

        actor = await make_actor('with-actor-init', main_func=main)

        run_result = await actor.call()

        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'


class TestActorExit:

    async def test_actor_exit_code(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                input = await Actor.get_input()
                await Actor.exit(**input)

        actor = await make_actor('actor-exit', main_func=main)

        for exit_code in [0, 1, 101]:
            run_result = await actor.call(run_input={'exit_code': exit_code})
            assert run_result is not None
            assert run_result['exitCode'] == exit_code
            assert run_result['status'] == 'FAILED' if exit_code > 0 else 'SUCCEEDED'


class TestActorFail:

    async def test_fail_exit_code(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                input = await Actor.get_input()
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

    async def test_with_actor_fail_correctly(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                raise Exception('This is a test exception')

        actor = await make_actor('with-actor-fail', main_func=main)
        run_result = await actor.call()
        assert run_result is not None
        assert run_result['exitCode'] == 91
        assert run_result['status'] == 'FAILED'


class TestActorMain:

    async def test_actor_main(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async def actor_function() -> None:
                input = await Actor.get_input()
                if input.get('raise_exception'):
                    raise Exception(input.get('raise_exception'))
                elif input.get('exit_code'):
                    await Actor.exit(exit_code=input.get('exit_code'))
                elif input.get('fail'):
                    await Actor.fail()
                elif input.get('set_output'):
                    await Actor.set_value('OUTPUT', input.get('set_output'))
                print('Main function called')

            await Actor.main(actor_function)

        actor = await make_actor('actor-main', main_func=main)

        exception_run = await actor.call(run_input={'raise_exception': 'This is a test exception'})
        assert exception_run is not None
        assert exception_run['status'] == 'FAILED'
        assert exception_run['exitCode'] == 91

        exit_code = 10
        exited_run = await actor.call(run_input={'exit_code': exit_code})
        assert exited_run is not None
        assert exited_run['status'] == 'FAILED'
        assert exited_run['exitCode'] == exit_code

        failed_run = await actor.call(run_input={'fail': True})
        assert failed_run is not None
        assert failed_run['status'] == 'FAILED'
        assert failed_run['exitCode'] == 1

        test_output = {'test': 'output'}
        run_with_output = await actor.call(run_input={'set_output': test_output})
        assert run_with_output is not None
        assert run_with_output['status'] == 'SUCCEEDED'
        output = await actor.last_run().key_value_store().get_record('OUTPUT')
        assert output is not None
        assert output['value'] == test_output
