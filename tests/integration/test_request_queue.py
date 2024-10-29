from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from apify_client import ApifyClientAsync

    from .conftest import ActorFactory


async def test_add_and_fetch_requests(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    async def main() -> None:
        async with Actor:
            desired_request_count = 100
            print('Opening request queue...')
            # I have seen it get stuck on this call
            rq = await Actor.open_request_queue()
            # Add some requests
            for i in range(desired_request_count):
                print(f'Adding request {i}...')
                await rq.add_request(f'https://example.com/{i}')

            handled_request_count = 0
            while next_request := await rq.fetch_next_request():
                print('Fetching next request...')
                queue_operation_info = await rq.mark_request_as_handled(next_request)
                assert queue_operation_info is not None
                assert queue_operation_info.was_already_handled is False
                handled_request_count += 1

            assert handled_request_count == desired_request_count
            print('Waiting for queue to be finished...')
            is_finished = await rq.is_finished()
            assert is_finished is True

    actor = await make_actor('rq-simple-test', main_func=main)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'


async def test_add_requests_in_batches(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    async def main() -> None:
        async with Actor:
            desired_request_count = 100
            print('Opening request queue...')
            # I have seen it get stuck on this call
            rq = await Actor.open_request_queue()
            # Add some requests
            await rq.add_requests_batched([f'https://example.com/{i}' for i in range(desired_request_count)])

            handled_request_count = 0
            while next_request := await rq.fetch_next_request():
                print('Fetching next request...')
                queue_operation_info = await rq.mark_request_as_handled(next_request)
                assert queue_operation_info is not None
                assert queue_operation_info.was_already_handled is False
                handled_request_count += 1

            assert handled_request_count == desired_request_count
            print('Waiting for queue to be finished...')
            is_finished = await rq.is_finished()
            assert is_finished is True

    actor = await make_actor('rq-batch-test', main_func=main)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'


async def test_add_non_unique_requests_in_batch(
    apify_client_async: ApifyClientAsync,
    make_actor: ActorFactory,
) -> None:
    async def main() -> None:
        from crawlee import Request

        async with Actor:
            desired_request_count = 100
            print('Opening request queue...')
            # I have seen it get stuck on this call
            rq = await Actor.open_request_queue()
            # Add some requests
            await rq.add_requests_batched(
                [
                    Request.from_url(f'https://example.com/{i}', unique_key=str(i - 1 if i % 4 == 1 else i))
                    for i in range(desired_request_count)
                ]
            )

            handled_request_count = 0
            while next_request := await rq.fetch_next_request():
                print('Fetching next request...')
                queue_operation_info = await rq.mark_request_as_handled(next_request)
                assert queue_operation_info is not None
                assert queue_operation_info.was_already_handled is False
                handled_request_count += 1

            assert handled_request_count == desired_request_count * 3 / 4
            print('Waiting for queue to be finished...')
            is_finished = await rq.is_finished()
            assert is_finished is True

    actor = await make_actor('rq-batch-test', main_func=main)

    call_result = await actor.call()
    assert call_result is not None

    run_client = apify_client_async.run(call_result['id'])
    run_result = await run_client.wait_for_finish(wait_secs=300)

    assert run_result is not None
    assert run_result['status'] == 'SUCCEEDED'
