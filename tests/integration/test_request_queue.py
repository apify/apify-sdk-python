from apify import Actor

from .conftest import ActorFactory


class TestRequestQueue:
    async def test_simple(self, make_actor: ActorFactory) -> None:
        async def main() -> None:
            async with Actor:
                desired_request_count = 100
                print('Opening request queue...')
                # I have seen it get stuck on this call
                rq = await Actor.open_request_queue()
                # Add some requests
                for i in range(desired_request_count):
                    print(f'Adding request {i}...')
                    await rq.add_request({
                        'url': f'https://example.com/{i}',
                    })

                handled_request_count = 0
                while next_request := await rq.fetch_next_request():
                    print('Fetching next request...')
                    queue_operation_info = await rq.mark_request_as_handled(next_request)
                    assert queue_operation_info is not None
                    assert queue_operation_info['wasAlreadyHandled'] is False
                    handled_request_count += 1

                assert handled_request_count == desired_request_count
                print('Waiting for queue to be finished...')
                is_finished = await rq.is_finished()
                assert is_finished is True

        actor = await make_actor('rq-simple-test', main_func=main)

        run_result = await actor.call()
        assert run_result is not None
        assert run_result['status'] == 'SUCCEEDED'
