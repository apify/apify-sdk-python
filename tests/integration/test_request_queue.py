from __future__ import annotations

from typing import TYPE_CHECKING

from apify import Actor

if TYPE_CHECKING:
    from .conftest import MakeActorFunction, RunActorFunction


async def test_add_and_fetch_requests(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test basic functionality of adding and fetching requests."""

    async def main() -> None:
        async with Actor:
            desired_request_count = 100
            Actor.log.info('Opening request queue...')
            rq = await Actor.open_request_queue()

            # Add some requests
            for i in range(desired_request_count):
                Actor.log.info(f'Adding request {i}...')
                await rq.add_request(f'https://example.com/{i}')

            handled_request_count = 0
            while next_request := await rq.fetch_next_request():
                Actor.log.info('Fetching next request...')
                queue_operation_info = await rq.mark_request_as_handled(next_request)
                assert queue_operation_info is not None
                assert queue_operation_info.was_already_handled is False
                handled_request_count += 1

            assert handled_request_count == desired_request_count
            Actor.log.info('Waiting for queue to be finished...')
            is_finished = await rq.is_finished()
            assert is_finished is True

    actor = await make_actor(label='rq-simple-test', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_add_requests_in_batches(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test adding multiple requests in a single batch operation."""

    async def main() -> None:
        async with Actor:
            desired_request_count = 100
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add some requests
            await rq.add_requests_batched([f'https://example.com/{i}' for i in range(desired_request_count)])
            total_count = await rq.get_total_count()
            Actor.log.info(f'Added {desired_request_count} requests in batch, total in queue: {total_count}')

            handled_request_count = 0
            while next_request := await rq.fetch_next_request():
                if handled_request_count % 20 == 0:
                    Actor.log.info(f'Processing request {handled_request_count + 1}...')
                queue_operation_info = await rq.mark_request_as_handled(next_request)
                assert queue_operation_info is not None
                assert queue_operation_info.was_already_handled is False
                handled_request_count += 1

            assert handled_request_count == desired_request_count
            is_finished = await rq.is_finished()
            Actor.log.info(f'Processed {handled_request_count} requests, queue finished: {is_finished}')
            assert is_finished is True

    actor = await make_actor(label='rq-batch-test', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_add_non_unique_requests_in_batch(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test adding requests with duplicate unique keys in batch."""

    async def main() -> None:
        from apify import Request

        async with Actor:
            desired_request_count = 100
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add some requests
            requests_to_add = [
                Request.from_url(f'https://example.com/{i}', unique_key=str(i - 1 if i % 4 == 1 else i))
                for i in range(desired_request_count)
            ]
            await rq.add_requests_batched(requests_to_add)
            total_count = await rq.get_total_count()
            Actor.log.info(
                f'Added {desired_request_count} requests with duplicate unique keys, total in queue: {total_count}'
            )

            handled_request_count = 0
            while next_request := await rq.fetch_next_request():
                if handled_request_count % 20 == 0:
                    Actor.log.info(f'Processing request {handled_request_count + 1}: {next_request.url}')
                queue_operation_info = await rq.mark_request_as_handled(next_request)
                assert queue_operation_info is not None
                assert queue_operation_info.was_already_handled is False
                handled_request_count += 1

            expected_count = int(desired_request_count * 3 / 4)
            assert handled_request_count == expected_count
            is_finished = await rq.is_finished()
            Actor.log.info(f'Processed {handled_request_count}/{expected_count} requests, finished: {is_finished}')
            assert is_finished is True

    actor = await make_actor(label='rq-batch-test', main_func=main)
    run_result = await run_actor(actor)

    assert run_result.status == 'SUCCEEDED'


async def test_queue_forefront_ordering(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that forefront requests are processed before regular requests."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add regular requests
            await rq.add_request('https://example.com/1')
            await rq.add_request('https://example.com/2')
            await rq.add_request('https://example.com/3')
            Actor.log.info('Added 3 regular requests')

            # Add forefront requests
            await rq.add_request('https://example.com/priority1', forefront=True)
            await rq.add_request('https://example.com/priority2', forefront=True)
            total_count = await rq.get_total_count()
            Actor.log.info(f'Added 2 forefront requests, total in queue: {total_count}')

            # Fetch requests and verify order
            fetched_urls = []
            while next_request := await rq.fetch_next_request():
                Actor.log.info(f'Fetched request: {next_request.url}')
                fetched_urls.append(next_request.url)
                await rq.mark_request_as_handled(next_request)

            # Forefront requests should come first (in reverse order of addition)
            assert fetched_urls[0] == 'https://example.com/priority2'
            assert fetched_urls[1] == 'https://example.com/priority1'
            assert 'https://example.com/1' in fetched_urls[2:]
            assert 'https://example.com/2' in fetched_urls[2:]
            assert 'https://example.com/3' in fetched_urls[2:]
            Actor.log.info(f'Forefront ordering verified: {fetched_urls}')

    actor = await make_actor(label='rq-forefront-order-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_duplicate_requests_by_unique_key(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that requests with the same unique_key are not duplicated."""

    async def main() -> None:
        from apify import Request

        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add requests with the same unique key
            request1 = Request.from_url('https://example.com/page1', unique_key='same-key')
            request2 = Request.from_url('https://example.com/page2', unique_key='same-key')
            request3 = Request.from_url('https://example.com/page3', unique_key='different-key')

            result1 = await rq.add_request(request1)
            result2 = await rq.add_request(request2)
            result3 = await rq.add_request(request3)
            Actor.log.info(
                f'Added 3 requests: was_already_present=[{result1.was_already_present}, '
                f'{result2.was_already_present}, {result3.was_already_present}]'
            )

            # Second request should be marked as already present
            assert result1.was_already_present is False
            assert result2.was_already_present is True
            assert result3.was_already_present is False

            # Only 2 requests should be fetchable
            fetched_count = 0
            while next_request := await rq.fetch_next_request():
                fetched_count += 1
                Actor.log.info(f'Fetched request {fetched_count}: {next_request.url}')
                await rq.mark_request_as_handled(next_request)

            assert fetched_count == 2
            Actor.log.info(f'Deduplication verified: fetched {fetched_count} unique requests from 3 added')

    actor = await make_actor(label='rq-duplicate-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_request_reclaim_functionality(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test request reclaiming for failed processing."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add a test request
            await rq.add_request('https://example.com/test')
            Actor.log.info('Added test request')

            # Fetch and reclaim the request
            request = await rq.fetch_next_request()
            assert request is not None
            Actor.log.info(f'Fetched request: {request.url}')

            # Reclaim the request (simulate failed processing)
            reclaim_result = await rq.reclaim_request(request)
            assert reclaim_result is not None
            assert reclaim_result.was_already_handled is False
            Actor.log.info('Request reclaimed successfully')

            # Should be able to fetch the same request again
            request2 = await rq.fetch_next_request()
            assert request2 is not None
            assert request2.url == request.url
            Actor.log.info(f'Successfully fetched reclaimed request: {request2.url}')

            # Mark as handled this time
            await rq.mark_request_as_handled(request2)
            is_finished = await rq.is_finished()
            Actor.log.info(f'Request marked as handled, queue finished: {is_finished}')
            assert is_finished is True

    actor = await make_actor(label='rq-reclaim-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_request_reclaim_with_forefront(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test reclaiming requests to the front of the queue."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add multiple requests
            await rq.add_request('https://example.com/1')
            await rq.add_request('https://example.com/2')
            await rq.add_request('https://example.com/3')
            Actor.log.info('Added 3 requests')

            # Fetch first request
            first_request = await rq.fetch_next_request()
            assert first_request is not None
            Actor.log.info(f'Fetched first request: {first_request.url}')

            # Reclaim to forefront
            await rq.reclaim_request(first_request, forefront=True)
            Actor.log.info('Request reclaimed to forefront')

            # The reclaimed request should be fetched first again
            next_request = await rq.fetch_next_request()
            assert next_request is not None
            assert next_request.url == first_request.url
            Actor.log.info(f'Confirmed reclaimed request came first: {next_request.url}')

            # Clean up
            await rq.mark_request_as_handled(next_request)
            remaining_count = 0
            while True:
                remaining_request = await rq.fetch_next_request()
                if remaining_request is None:
                    break
                remaining_count += 1
                await rq.mark_request_as_handled(remaining_request)

            Actor.log.info(f'Test completed - processed {remaining_count} additional requests')

    actor = await make_actor(label='rq-reclaim-forefront-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_complex_request_objects(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test handling complex Request objects with various properties."""

    async def main() -> None:
        from apify import Request

        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Create request with various properties
            request = Request.from_url(
                'https://example.com/api/data',
                method='POST',
                headers={'Authorization': 'Bearer token123', 'Content-Type': 'application/json'},
                user_data={'category': 'api', 'priority': 'high'},
                unique_key='api-request-1',
            )
            await rq.add_request(request)
            Actor.log.info(f'Added complex request: {request.url} with method {request.method}')

            # Fetch and verify all properties are preserved
            fetched_request = await rq.fetch_next_request()
            assert fetched_request is not None
            Actor.log.info(f'Fetched request: {fetched_request.url}')

            assert fetched_request.url == 'https://example.com/api/data'
            assert fetched_request.method == 'POST'
            assert fetched_request.headers['Authorization'] == 'Bearer token123'
            assert fetched_request.headers['Content-Type'] == 'application/json'
            assert fetched_request.user_data['category'] == 'api'
            assert fetched_request.user_data['priority'] == 'high'
            assert fetched_request.unique_key == 'api-request-1'
            Actor.log.info('All properties verified successfully')

            await rq.mark_request_as_handled(fetched_request)
            Actor.log.info('Complex request test completed')

    actor = await make_actor(label='rq-complex-request-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_get_request_by_id(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test retrieving specific requests by their ID."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add a request and get its ID
            add_result = await rq.add_request('https://example.com/test')
            request_id = add_result.id
            Actor.log.info(f'Request added with ID: {request_id}')

            # Retrieve the request by ID
            retrieved_request = await rq.get_request(request_id)
            assert retrieved_request is not None
            assert retrieved_request.url == 'https://example.com/test'
            assert retrieved_request.id == request_id
            Actor.log.info('Request retrieved successfully by ID')

            # Test with non-existent ID
            non_existent_request = await rq.get_request('non-existent-id')
            assert non_existent_request is None
            Actor.log.info('Non-existent ID correctly returned None')

    actor = await make_actor(label='rq-get-by-id-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_queue_metadata_tracking(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test request queue metadata and counts."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Check initial state
            initial_total = await rq.get_total_count()
            initial_handled = await rq.get_handled_count()
            Actor.log.info(f'Initial state - Total: {initial_total}, Handled: {initial_handled}')
            assert initial_total == 0
            assert initial_handled == 0

            # Add requests
            await rq.add_requests_batched([f'https://example.com/{i}' for i in range(5)])
            Actor.log.info('Added 5 requests in batch')

            # Check counts after adding
            total_after_add = await rq.get_total_count()
            handled_after_add = await rq.get_handled_count()
            Actor.log.info(f'After adding - Total: {total_after_add}, Handled: {handled_after_add}')
            assert total_after_add == 5
            assert handled_after_add == 0

            # Process some requests
            for _ in range(3):
                request = await rq.fetch_next_request()
                if request:
                    await rq.mark_request_as_handled(request)

            Actor.log.info('Processed 3 requests')

            # Check counts after processing
            final_total = await rq.get_total_count()
            final_handled = await rq.get_handled_count()
            Actor.log.info(f'Final state - Total: {final_total}, Handled: {final_handled}')
            assert final_total == 5
            assert final_handled == 3

    actor = await make_actor(label='rq-metadata-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_batch_operations_performance(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test batch operations vs individual operations."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Test batch add vs individual adds
            batch_requests = [f'https://example.com/batch/{i}' for i in range(50)]
            Actor.log.info(f'Prepared {len(batch_requests)} requests for batch add')

            # Add in batch
            await rq.add_requests_batched(batch_requests)
            Actor.log.info('Batch add completed')

            # Verify all requests were added
            total_count = await rq.get_total_count()
            handled_count = await rq.get_handled_count()
            Actor.log.info(f'After batch add - Total: {total_count}, Handled: {handled_count}')
            assert total_count == 50
            assert handled_count == 0

            # Process all requests
            processed_count = 0
            while next_request := await rq.fetch_next_request():
                processed_count += 1
                await rq.mark_request_as_handled(next_request)
                if processed_count >= 50:  # Safety break
                    break

            Actor.log.info(f'Processing completed. Total processed: {processed_count}')
            assert processed_count == 50

            is_finished = await rq.is_finished()
            Actor.log.info(f'Queue finished state: {is_finished}')

    actor = await make_actor(label='rq-batch-performance-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_queue_state_consistency(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test queue state consistency during concurrent operations."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add initial requests
            for i in range(10):
                await rq.add_request(f'https://example.com/{i}')
            Actor.log.info('Added 10 initial requests')

            initial_total = await rq.get_total_count()
            Actor.log.info(f'Initial total count: {initial_total}')

            # Simulate some requests being processed and others being reclaimed
            processed_requests = []
            reclaimed_requests = []

            for i in range(5):
                request = await rq.fetch_next_request()
                if request:
                    if i % 2 == 0:  # Process even indices
                        await rq.mark_request_as_handled(request)
                        processed_requests.append(request)
                    else:  # Reclaim odd indices
                        await rq.reclaim_request(request)
                        reclaimed_requests.append(request)

            Actor.log.info(f'Processed {len(processed_requests)} requests, reclaimed {len(reclaimed_requests)}')

            # Verify queue state
            expected_handled = len(processed_requests)
            current_handled = await rq.get_handled_count()
            current_total = await rq.get_total_count()

            Actor.log.info(f'Expected handled: {expected_handled}, Actual handled: {current_handled}')
            Actor.log.info(f'Current total: {current_total}')

            assert current_handled == expected_handled
            assert current_total == 10

            # Process remaining requests
            remaining_count = 0
            while next_request := await rq.fetch_next_request():
                remaining_count += 1
                await rq.mark_request_as_handled(next_request)

            Actor.log.info(f'Processed {remaining_count} remaining requests')
            is_finished = await rq.is_finished()
            Actor.log.info(f'Queue finished state: {is_finished}')
            assert is_finished is True

    actor = await make_actor(label='rq-state-consistency-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_empty_queue_behavior(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test behavior with empty queues."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Test empty queue operations
            is_empty = await rq.is_empty()
            is_finished = await rq.is_finished()
            Actor.log.info(f'Empty queue - is_empty: {is_empty}, is_finished: {is_finished}')
            assert is_empty is True
            assert is_finished is True

            # Fetch from empty queue
            request = await rq.fetch_next_request()
            Actor.log.info(f'Fetch result from empty queue: {request}')
            assert request is None

            # Check metadata for empty queue
            metadata = await rq.get_info()
            assert metadata is not None
            Actor.log.info(
                f'Empty queue metadata - Total: {metadata.total_request_count}, '
                f'Handled: {metadata.handled_request_count}, '
                f'Pending: {metadata.pending_request_count}'
            )
            assert metadata.total_request_count == 0
            assert metadata.handled_request_count == 0
            assert metadata.pending_request_count == 0

    actor = await make_actor(label='rq-empty-queue-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_large_batch_operations(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test handling large batches of requests."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Create a large batch of requests
            large_batch = [f'https://example.com/large/{i}' for i in range(500)]
            Actor.log.info(f'Created batch of {len(large_batch)} requests')

            # Add in batch
            await rq.add_requests_batched(large_batch, batch_size=100, wait_for_all_requests_to_be_added=True)
            Actor.log.info('Large batch add completed')

            # Verify all requests were added
            total_count = await rq.get_total_count()
            Actor.log.info(f'Total requests in queue after batch add: {total_count}')
            assert total_count == 500

            # Process all in chunks to test performance
            processed_count = 0
            chunk_number = 0
            while not await rq.is_empty():
                chunk_number += 1

                # Process in chunks of 50
                for _ in range(50):
                    request = await rq.fetch_next_request()
                    if request:
                        await rq.mark_request_as_handled(request)
                        processed_count += 1
                    else:
                        break

                if processed_count >= 500:
                    break

            Actor.log.info(f'Processing completed. Total processed: {processed_count}')
            assert processed_count == 500

            is_finished = await rq.is_finished()
            Actor.log.info(f'Queue finished state: {is_finished}')
            assert is_finished is True

    actor = await make_actor(label='rq-large-batch-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_mixed_string_and_request_objects(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test adding both string URLs and Request objects."""

    async def main() -> None:
        from apify import Request

        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add string URLs
            await rq.add_request('https://example.com/string1')
            await rq.add_request('https://example.com/string2')
            Actor.log.info('Added string URL requests')

            # Add Request objects
            request_obj = Request.from_url('https://example.com/object1', user_data={'type': 'request_object'})
            await rq.add_request(request_obj)
            Actor.log.info('Added Request object with user_data')

            # Add mixed batch
            mixed_batch: list[str | Request] = [
                'https://example.com/mixed1',
                Request.from_url('https://example.com/mixed2', method='POST'),
                'https://example.com/mixed3',
            ]
            await rq.add_requests_batched(mixed_batch)
            Actor.log.info('Added mixed batch of strings and Request objects')

            total_count = await rq.get_total_count()
            Actor.log.info(f'Total requests in queue: {total_count}')

            # Fetch and verify all types work
            fetched_requests = []
            while next_request := await rq.fetch_next_request():
                fetched_requests.append(next_request)
                await rq.mark_request_as_handled(next_request)

            Actor.log.info(f'Total fetched requests: {len(fetched_requests)}')
            assert len(fetched_requests) == 6

            # Find the request object we added
            request_obj_found = None
            for req in fetched_requests:
                if req.user_data and req.user_data.get('type') == 'request_object':
                    request_obj_found = req
                    break

            assert request_obj_found is not None
            assert request_obj_found.url == 'https://example.com/object1'
            Actor.log.info('Mixed types verified - found request object with user_data')

    actor = await make_actor(label='rq-mixed-types-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_concurrent_processing_simulation(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test simulation of concurrent request processing."""

    async def main() -> None:
        import asyncio

        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add requests for concurrent processing
            for i in range(20):
                await rq.add_request(f'https://example.com/concurrent/{i}')
            Actor.log.info('Added 20 requests for concurrent processing')

            total_count = await rq.get_total_count()
            Actor.log.info(f'Total requests in queue: {total_count}')

            # Simulate concurrent workers
            async def worker(_worker_id: int) -> int:
                processed = 0
                while True:
                    request = await rq.fetch_next_request()
                    if request is None:
                        break

                    # Simulate some work
                    await asyncio.sleep(0.01)

                    # Randomly reclaim some requests (simulate failures)
                    if processed % 7 == 0 and processed > 0:  # Reclaim every 7th request
                        await rq.reclaim_request(request)
                    else:
                        await rq.mark_request_as_handled(request)
                        processed += 1

                return processed

            # Run multiple workers concurrently
            workers = [worker(i) for i in range(3)]
            results = await asyncio.gather(*workers)

            total_processed = sum(results)
            Actor.log.info(f'Total processed by workers: {total_processed}')
            Actor.log.info(f'Individual worker results: {results}')

            # Process any remaining reclaimed requests
            remaining_count = 0
            while not await rq.is_finished():
                request = await rq.fetch_next_request()
                if request:
                    remaining_count += 1
                    await rq.mark_request_as_handled(request)
                else:
                    break

            Actor.log.info(f'Processed {remaining_count} remaining requests')
            is_finished = await rq.is_finished()
            Actor.log.info(f'Queue finished state: {is_finished}')
            assert is_finished is True

    actor = await make_actor(label='rq-concurrent-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_queue_persistence_across_operations(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that queue state persists across different operations."""

    async def main() -> None:
        async with Actor:
            # Open queue and add some requests
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add initial batch
            initial_requests = [f'https://example.com/persist/{i}' for i in range(10)]
            await rq.add_requests_batched(initial_requests, wait_for_all_requests_to_be_added=True)
            Actor.log.info(f'Added initial batch of {len(initial_requests)} requests')

            initial_total = await rq.get_total_count()
            Actor.log.info(f'Total count after initial batch: {initial_total}')

            # Process some requests
            processed_count = 0
            for _ in range(5):
                request = await rq.fetch_next_request()
                if request:
                    await rq.mark_request_as_handled(request)
                    processed_count += 1

            Actor.log.info(f'Processed {processed_count} requests from initial batch')
            handled_after_first_batch = await rq.get_handled_count()
            Actor.log.info(f'Handled count after processing: {handled_after_first_batch}')

            # Add more requests
            additional_requests = [f'https://example.com/additional/{i}' for i in range(5)]
            await rq.add_requests_batched(additional_requests, wait_for_all_requests_to_be_added=True)
            Actor.log.info(f'Added additional batch of {len(additional_requests)} requests')

            # Check final state
            total_after_additional = await rq.get_total_count()
            handled_after_additional = await rq.get_handled_count()
            Actor.log.info(
                f'After adding additional batch - Total: {total_after_additional}, Handled: {handled_after_additional}'
            )
            assert total_after_additional == 15
            assert handled_after_additional == 5

            # Process remaining
            remaining_processed = 0
            while not await rq.is_finished():
                request = await rq.fetch_next_request()
                if request:
                    remaining_processed += 1
                    await rq.mark_request_as_handled(request)
                else:
                    break

            Actor.log.info(f'Processed {remaining_processed} remaining requests')
            is_finished = await rq.is_finished()
            final_total = await rq.get_total_count()
            final_handled = await rq.get_handled_count()

            Actor.log.info(f'Final state - Finished: {is_finished}, Total: {final_total}, Handled: {final_handled}')
            assert is_finished is True
            assert final_total == 15
            assert final_handled == 15

    actor = await make_actor(label='rq-persistence-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_request_deduplication_edge_cases(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test edge cases in request deduplication."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Test URL normalization and deduplication
            urls = [
                'https://example.com/page',
                'https://example.com/page/',  # Should be deduplicated
                'https://example.com/page?',  # Should be deduplicated
                'https://example.com/page#fragment',  # Different unique key
                'https://example.com/page?param=1',  # Different unique key
            ]
            Actor.log.info(f'Testing deduplication with {len(urls)} URLs')

            results = []
            for url in urls:
                result = await rq.add_request(url)
                results.append(result.was_already_present)

            Actor.log.info(f'was_already_present results: {results}')

            # Fetch all unique requests
            fetched_urls = []
            while next_request := await rq.fetch_next_request():
                fetched_urls.append(next_request.url)
                await rq.mark_request_as_handled(next_request)

            # Should have fewer requests than URLs due to deduplication
            assert len(fetched_urls) < len(urls)
            Actor.log.info(f'Added {len(urls)} URLs, got {len(fetched_urls)} unique requests')

    actor = await make_actor(label='rq-deduplication-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_request_ordering_with_mixed_operations(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test request ordering with mixed add/reclaim operations."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add initial requests
            await rq.add_request('https://example.com/1')
            await rq.add_request('https://example.com/2')
            Actor.log.info('Added initial requests')

            # Fetch one and reclaim to forefront
            request1 = await rq.fetch_next_request()
            assert request1 is not None
            assert request1.url == 'https://example.com/1'
            Actor.log.info(f'Fetched request: {request1.url}')

            await rq.reclaim_request(request1, forefront=True)
            Actor.log.info('Reclaimed request to forefront')

            # Add forefront request
            await rq.add_request('https://example.com/priority', forefront=True)
            Actor.log.info('Added new forefront request')

            # Fetch all requests and verify forefront behavior
            urls_ordered = list[str]()
            while next_request := await rq.fetch_next_request():
                urls_ordered.append(next_request.url)
                await rq.mark_request_as_handled(next_request)

            Actor.log.info(f'Final order of fetched URLs: {urls_ordered}')

            # Verify that we got all 3 requests
            assert len(urls_ordered) == 3

            assert urls_ordered[0] == 'https://example.com/priority'
            assert urls_ordered[1] == request1.url
            assert urls_ordered[2] == 'https://example.com/2'
            Actor.log.info('Request ordering verified successfully')

    actor = await make_actor(label='rq-mixed-ordering-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_request_queue_isolation(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test that different request queues are properly isolated."""

    async def main() -> None:
        async with Actor:
            # Open multiple queues
            rq1 = await Actor.open_request_queue(name='queue-1')
            rq2 = await Actor.open_request_queue(name='queue-2')
            Actor.log.info('Opened two separate named queues')

            # Verify they are different instances
            assert rq1 is not rq2
            Actor.log.info('Verified queues are different instances')

            # Add different requests to each queue
            await rq1.add_request('https://example.com/queue1-request')
            await rq2.add_request('https://example.com/queue2-request')
            Actor.log.info('Added different requests to each queue')

            # Verify isolation
            req1 = await rq1.fetch_next_request()
            req2 = await rq2.fetch_next_request()

            assert req1 is not None
            assert 'queue1' in req1.url
            assert req2 is not None
            assert 'queue2' in req2.url
            Actor.log.info(f'Queue 1 request: {req1.url}')
            Actor.log.info(f'Queue 2 request: {req2.url}')
            Actor.log.info('Queue isolation verified successfully')

            # Clean up
            await rq1.mark_request_as_handled(req1)
            await rq2.mark_request_as_handled(req2)

            # Drop queues
            await rq1.drop()
            await rq2.drop()
            Actor.log.info('Dropped both queues')

    actor = await make_actor(label='rq-isolation-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_request_unique_key_behavior(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test behavior of custom unique keys."""

    async def main() -> None:
        from apify import Request

        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Add requests with custom unique keys
            req1 = Request.from_url('https://example.com/page1', unique_key='custom-key-1')
            req2 = Request.from_url('https://example.com/page2', unique_key='custom-key-1')  # Same key
            req3 = Request.from_url('https://example.com/page3', unique_key='custom-key-2')  # Different key

            result1 = await rq.add_request(req1)
            result2 = await rq.add_request(req2)
            result3 = await rq.add_request(req3)

            Actor.log.info(
                f'Added requests - was_already_present: [{result1.was_already_present}, '
                f'{result2.was_already_present}, {result3.was_already_present}]'
            )

            # Second request should be marked as already present
            assert result1.was_already_present is False
            assert result2.was_already_present is True
            assert result3.was_already_present is False

            # Only 2 requests should be fetchable
            fetched_count = 0
            fetched_requests = []
            while next_request := await rq.fetch_next_request():
                fetched_count += 1
                fetched_requests.append(next_request)
                await rq.mark_request_as_handled(next_request)

            Actor.log.info(f'Total fetched requests: {fetched_count}')
            assert fetched_count == 2

            # Verify the fetched requests have the correct unique keys
            unique_keys = {req.unique_key for req in fetched_requests}
            Actor.log.info(f'Unique keys in fetched requests: {unique_keys}')
            assert unique_keys == {'custom-key-1', 'custom-key-2'}

    actor = await make_actor(label='rq-unique-key-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_queue_finished_state_accuracy(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test accuracy of is_finished() method in various scenarios."""

    async def main() -> None:
        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Initially should be finished
            initial_finished = await rq.is_finished()
            Actor.log.info(f'Initial finished state: {initial_finished}')
            assert initial_finished is True

            # Add requests - should not be finished
            await rq.add_request('https://example.com/test1')
            await rq.add_request('https://example.com/test2')
            after_add_finished = await rq.is_finished()
            Actor.log.info(f'Finished state after adding requests: {after_add_finished}')
            assert after_add_finished is False

            # Fetch but don't handle - should not be finished
            request1 = await rq.fetch_next_request()
            assert request1 is not None
            after_fetch_finished = await rq.is_finished()
            Actor.log.info(f'Finished state after fetch (not handled): {after_fetch_finished}')
            assert after_fetch_finished is False

            # Reclaim request - should still not be finished
            await rq.reclaim_request(request1)
            after_reclaim_finished = await rq.is_finished()
            Actor.log.info(f'Finished state after reclaim: {after_reclaim_finished}')
            assert after_reclaim_finished is False

            # Handle all requests - should be finished
            processed_count = 0
            while next_request := await rq.fetch_next_request():
                processed_count += 1
                await rq.mark_request_as_handled(next_request)

            Actor.log.info(f'Processed {processed_count} requests')
            final_finished = await rq.is_finished()
            Actor.log.info(f'Final finished state after processing all: {final_finished}')
            assert final_finished is True

    actor = await make_actor(label='rq-finished-state-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'


async def test_queue_operations_performance_pattern(
    make_actor: MakeActorFunction,
    run_actor: RunActorFunction,
) -> None:
    """Test a common performance pattern: producer-consumer."""

    async def main() -> None:
        import asyncio

        async with Actor:
            rq = await Actor.open_request_queue()
            Actor.log.info('Request queue opened')

            # Producer: Add requests in background
            async def producer() -> None:
                for i in range(20):
                    await rq.add_request(f'https://example.com/item/{i}')
                    if i % 5 == 0:  # Add some delay to simulate real production
                        await asyncio.sleep(0.01)
                Actor.log.info('Producer finished adding all 20 requests')

            # Consumer: Process requests as they become available
            async def consumer() -> int:
                processed = 0
                consecutive_empty = 0
                max_empty_attempts = 5

                while consecutive_empty < max_empty_attempts:
                    request = await rq.fetch_next_request()
                    if request is None:
                        consecutive_empty += 1
                        await asyncio.sleep(0.01)  # Brief wait for more requests
                        continue

                    consecutive_empty = 0
                    await rq.mark_request_as_handled(request)
                    processed += 1

                Actor.log.info(f'Consumer finished initial processing, processed {processed} requests')
                return processed

            # Run producer and consumer concurrently
            producer_task = asyncio.create_task(producer())
            consumer_task = asyncio.create_task(consumer())

            # Wait for both to complete
            await producer_task
            processed_count = await consumer_task
            Actor.log.info(f'Concurrent phase completed, processed {processed_count} requests')

            # Process any remaining requests
            remaining_count = 0
            while next_request := await rq.fetch_next_request():
                await rq.mark_request_as_handled(next_request)
                processed_count += 1
                remaining_count += 1

            Actor.log.info(f'Processed {remaining_count} remaining requests')
            Actor.log.info(f'Total processed: {processed_count} requests')
            assert processed_count == 20

            final_finished = await rq.is_finished()
            Actor.log.info(f'Final queue finished state: {final_finished}')
            assert final_finished is True

    actor = await make_actor(label='rq-performance-pattern-test', main_func=main)
    run_result = await run_actor(actor)
    assert run_result.status == 'SUCCEEDED'
