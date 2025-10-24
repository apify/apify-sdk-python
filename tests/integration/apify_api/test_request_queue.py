from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, cast
from unittest import mock

import pytest

from apify_shared.consts import ApifyEnvVars
from crawlee import service_locator
from crawlee.crawlers import BasicCrawler

from .._utils import generate_unique_resource_name
from apify import Actor, Request
from apify.storage_clients import ApifyStorageClient
from apify.storage_clients._apify._utils import unique_key_to_request_id
from apify.storages import RequestQueue

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from apify_client import ApifyClientAsync
    from crawlee._types import BasicCrawlingContext

    from apify.storage_clients._apify._models import ApifyRequestQueueMetadata


@pytest.fixture(params=['single', 'shared'])
async def request_queue_apify(
    apify_token: str, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> AsyncGenerator[RequestQueue]:
    """Create an instance of the Apify request queue on the platform and drop it when the test is finished."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        rq = await RequestQueue.open(storage_client=ApifyStorageClient(request_queue_access=request.param))
        yield rq
        await rq.drop()


async def test_add_and_fetch_requests(request_queue_apify: RequestQueue) -> None:
    """Test basic functionality of adding and fetching requests."""

    desired_request_count = 100
    Actor.log.info('Opening request queue...')
    rq = request_queue_apify

    # Add some requests
    for i in range(desired_request_count):
        Actor.log.info(f'Adding request {i}...')
        await rq.add_request(f'https://example.com/{i}')

    handled_request_count = 0
    while next_request := await rq.fetch_next_request():
        Actor.log.info('Fetching next request...')
        queue_operation_info = await rq.mark_request_as_handled(next_request)
        assert queue_operation_info is not None, f'queue_operation_info={queue_operation_info}'
        assert queue_operation_info.was_already_handled is False, (
            f'queue_operation_info.was_already_handled={queue_operation_info.was_already_handled}'
        )
        handled_request_count += 1

    assert handled_request_count == desired_request_count, (
        f'handled_request_count={handled_request_count}',
        f'desired_request_count={desired_request_count}',
    )
    Actor.log.info('Waiting for queue to be finished...')
    is_finished = await rq.is_finished()
    assert is_finished is True, f'is_finished={is_finished}'


async def test_add_requests_in_batches(request_queue_apify: RequestQueue) -> None:
    """Test adding multiple requests in a single batch operation."""

    desired_request_count = 100
    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add some requests
    await rq.add_requests([f'https://example.com/{i}' for i in range(desired_request_count)])
    total_count = await rq.get_total_count()
    Actor.log.info(f'Added {desired_request_count} requests in batch, total in queue: {total_count}')

    handled_request_count = 0
    while next_request := await rq.fetch_next_request():
        if handled_request_count % 20 == 0:
            Actor.log.info(f'Processing request {handled_request_count + 1}...')
        queue_operation_info = await rq.mark_request_as_handled(next_request)
        assert queue_operation_info is not None, f'queue_operation_info={queue_operation_info}'
        assert queue_operation_info.was_already_handled is False, (
            f'queue_operation_info.was_already_handled={queue_operation_info.was_already_handled}'
        )
        handled_request_count += 1

    assert handled_request_count == desired_request_count, (
        f'handled_request_count={handled_request_count}',
        f'desired_request_count={desired_request_count}',
    )
    is_finished = await rq.is_finished()
    assert is_finished is True, f'is_finished={is_finished}'


async def test_add_non_unique_requests_in_batch(request_queue_apify: RequestQueue) -> None:
    """Test adding requests with duplicate unique keys in batch."""

    desired_request_count = 100
    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add some requests
    requests_to_add = [
        Request.from_url(f'https://example.com/{i}', unique_key=str(i - 1 if i % 4 == 1 else i))
        for i in range(desired_request_count)
    ]
    await rq.add_requests(requests_to_add)
    total_count = await rq.get_total_count()
    Actor.log.info(f'Added {desired_request_count} requests with duplicate unique keys, total in queue: {total_count}')

    handled_request_count = 0
    while next_request := await rq.fetch_next_request():
        if handled_request_count % 20 == 0:
            Actor.log.info(f'Processing request {handled_request_count + 1}: {next_request.url}')
        queue_operation_info = await rq.mark_request_as_handled(next_request)
        assert queue_operation_info is not None, f'queue_operation_info={queue_operation_info}'
        assert queue_operation_info.was_already_handled is False, (
            f'queue_operation_info.was_already_handled={queue_operation_info.was_already_handled}'
        )
        handled_request_count += 1

    expected_count = int(desired_request_count * 3 / 4)
    assert handled_request_count == expected_count, (
        f'handled_request_count={handled_request_count}',
        f'expected_count={expected_count}',
    )
    is_finished = await rq.is_finished()
    Actor.log.info(f'Processed {handled_request_count}/{expected_count} requests, finished: {is_finished}')
    assert is_finished is True, f'is_finished={is_finished}'


async def test_forefront_requests_ordering(request_queue_apify: RequestQueue) -> None:
    """Test that forefront requests are processed before regular requests."""

    rq = request_queue_apify
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
    expected_order = [
        'https://example.com/priority2',
        'https://example.com/priority1',
        'https://example.com/1',
        'https://example.com/2',
        'https://example.com/3',
    ]
    assert fetched_urls == expected_order, (
        f'fetched_urls={fetched_urls}',
        f'expected_order={expected_order}',
    )


async def test_request_unique_key_behavior(request_queue_apify: RequestQueue) -> None:
    """Test behavior of custom unique keys."""

    rq = request_queue_apify
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
    assert result1.was_already_present is False, f'result1.was_already_present={result1.was_already_present}'
    assert result2.was_already_present is True, f'result2.was_already_present={result2.was_already_present}'
    assert result3.was_already_present is False, f'result3.was_already_present={result3.was_already_present}'

    # Only 2 requests should be fetchable
    fetched_count = 0
    fetched_requests = []
    while next_request := await rq.fetch_next_request():
        fetched_count += 1
        fetched_requests.append(next_request)
        await rq.mark_request_as_handled(next_request)

    assert fetched_count == 2, f'fetched_count={fetched_count}'

    # Verify the fetched requests have the correct unique keys
    unique_keys = {req.unique_key for req in fetched_requests}
    expected_keys = {'custom-key-1', 'custom-key-2'}
    assert unique_keys == expected_keys, (
        f'unique_keys={unique_keys}',
        f'expected_keys={expected_keys}',
    )


async def test_request_reclaim_functionality(request_queue_apify: RequestQueue) -> None:
    """Test request reclaiming for failed processing."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add a test request
    await rq.add_request('https://example.com/test')
    Actor.log.info('Added test request')

    # Fetch and reclaim the request
    request = await rq.fetch_next_request()
    assert request is not None, f'request={request}'
    Actor.log.info(f'Fetched request: {request.url}')

    # Reclaim the request (simulate failed processing)
    reclaim_result = await rq.reclaim_request(request)
    assert reclaim_result is not None, f'reclaim_result={reclaim_result}'
    assert reclaim_result.was_already_handled is False, (
        f'reclaim_result.was_already_handled={reclaim_result.was_already_handled}'
    )
    Actor.log.info('Request reclaimed successfully')

    # Should be able to fetch the same request again
    request2 = await rq.fetch_next_request()
    assert request2 is not None, f'request2={request2}'
    assert request2.url == request.url, (
        f'request2.url={request2.url}',
        f'request.url={request.url}',
    )
    Actor.log.info(f'Successfully fetched reclaimed request: {request2.url}')

    # Mark as handled this time
    await rq.mark_request_as_handled(request2)
    is_finished = await rq.is_finished()
    assert is_finished is True, f'is_finished={is_finished}'


async def test_request_reclaim_with_forefront(request_queue_apify: RequestQueue) -> None:
    """Test reclaiming requests to the front of the queue."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add multiple requests
    await rq.add_request('https://example.com/1')
    await rq.add_request('https://example.com/2')
    await rq.add_request('https://example.com/3')
    Actor.log.info('Added 3 requests')

    # Fetch first request
    first_request = await rq.fetch_next_request()
    assert first_request is not None, f'first_request={first_request}'
    Actor.log.info(f'Fetched first request: {first_request.url}')

    # Reclaim to forefront
    await rq.reclaim_request(first_request, forefront=True)
    Actor.log.info('Request reclaimed to forefront')

    # The reclaimed request should be fetched first again
    next_request = await rq.fetch_next_request()
    assert next_request is not None, f'next_request={next_request}'
    assert next_request.url == first_request.url, (
        f'next_request.url={next_request.url}',
        f'first_request.url={first_request.url}',
    )
    Actor.log.info(f'Confirmed reclaimed request came first: {next_request.url}')

    # Clean up
    await rq.mark_request_as_handled(next_request)
    remaining_count = 0

    while next_request := await rq.fetch_next_request():
        remaining_count += 1
        await rq.mark_request_as_handled(next_request)

    Actor.log.info(f'Test completed - processed {remaining_count} additional requests')


async def test_complex_request_objects(request_queue_apify: RequestQueue) -> None:
    """Test handling complex Request objects with various properties."""

    rq = request_queue_apify
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
    assert fetched_request is not None, f'fetched_request={fetched_request}'
    Actor.log.info(f'Fetched request: {fetched_request.url}')

    assert fetched_request.url == 'https://example.com/api/data', f'fetched_request.url={fetched_request.url}'
    assert fetched_request.method == 'POST', f'fetched_request.method={fetched_request.method}'
    assert fetched_request.headers['Authorization'] == 'Bearer token123', (
        f'fetched_request.headers["Authorization"]={fetched_request.headers["Authorization"]}'
    )
    assert fetched_request.headers['Content-Type'] == 'application/json', (
        f'fetched_request.headers["Content-Type"]={fetched_request.headers["Content-Type"]}'
    )
    assert fetched_request.user_data['category'] == 'api', (
        f'fetched_request.user_data["category"]={fetched_request.user_data["category"]}'
    )
    assert fetched_request.user_data['priority'] == 'high', (
        f'fetched_request.user_data["priority"]={fetched_request.user_data["priority"]}'
    )
    assert fetched_request.unique_key == 'api-request-1', f'fetched_request.unique_key={fetched_request.unique_key}'
    Actor.log.info('All properties verified successfully')

    await rq.mark_request_as_handled(fetched_request)
    Actor.log.info('Complex request test completed')


async def test_get_request_by_unique_key(request_queue_apify: RequestQueue) -> None:
    """Test retrieving specific requests by their unique_key."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add a request and get its unique_key
    add_result = await rq.add_request('https://example.com/test')
    request_unique_key = add_result.unique_key
    Actor.log.info(f'Request added with unique_key: {request_unique_key}')

    # Retrieve the request by unique_key
    retrieved_request = await rq.get_request(request_unique_key)
    assert retrieved_request is not None, f'retrieved_request={retrieved_request}'
    assert retrieved_request.url == 'https://example.com/test', f'retrieved_request.url={retrieved_request.url}'
    assert retrieved_request.unique_key == request_unique_key, (f'{request_unique_key=}',)
    Actor.log.info('Request retrieved successfully by unique_key')

    # Test with non-existent unique_key
    non_existent_request = await rq.get_request('non-existent-unique_key')
    assert non_existent_request is None, f'non_existent_request={non_existent_request}'
    Actor.log.info('Non-existent unique_key correctly returned None')


async def test_metadata_tracking(request_queue_apify: RequestQueue) -> None:
    """Test request queue metadata and counts."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Check initial state
    initial_total = await rq.get_total_count()
    initial_handled = await rq.get_handled_count()
    Actor.log.info(f'Initial state - Total: {initial_total}, Handled: {initial_handled}')
    assert initial_total == 0, f'initial_total={initial_total}'
    assert initial_handled == 0, f'initial_handled={initial_handled}'

    # Add requests
    await rq.add_requests([f'https://example.com/{i}' for i in range(5)])
    Actor.log.info('Added 5 requests in batch')

    # Check counts after adding
    total_after_add = await rq.get_total_count()
    handled_after_add = await rq.get_handled_count()
    Actor.log.info(f'After adding - Total: {total_after_add}, Handled: {handled_after_add}')
    assert total_after_add == 5, f'total_after_add={total_after_add}'
    assert handled_after_add == 0, f'handled_after_add={handled_after_add}'

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
    assert final_total == 5, f'final_total={final_total}'
    assert final_handled == 3, f'final_handled={final_handled}'


async def test_batch_operations_performance(request_queue_apify: RequestQueue) -> None:
    """Test batch operations vs individual operations."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Test batch add vs individual adds
    batch_requests = [f'https://example.com/batch/{i}' for i in range(50)]
    Actor.log.info(f'Prepared {len(batch_requests)} requests for batch add')

    # Add in batch
    await rq.add_requests(batch_requests)
    Actor.log.info('Batch add completed')

    # Verify all requests were added
    total_count = await rq.get_total_count()
    handled_count = await rq.get_handled_count()
    Actor.log.info(f'After batch add - Total: {total_count}, Handled: {handled_count}')
    assert total_count == 50, f'total_count={total_count}'
    assert handled_count == 0, f'handled_count={handled_count}'

    # Process all requests
    processed_count = 0
    while next_request := await rq.fetch_next_request():
        processed_count += 1
        await rq.mark_request_as_handled(next_request)
        if processed_count >= 50:  # Safety break
            break

    Actor.log.info(f'Processing completed. Total processed: {processed_count}')
    assert processed_count == 50, f'processed_count={processed_count}'

    is_finished = await rq.is_finished()
    assert is_finished is True, f'is_finished={is_finished}'


async def test_state_consistency(request_queue_apify: RequestQueue) -> None:
    """Test queue state consistency during concurrent operations."""

    rq = request_queue_apify
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

    assert current_handled == expected_handled, (
        f'current_handled={current_handled}',
        f'expected_handled={expected_handled}',
    )
    assert current_total == 10, f'current_total={current_total}'

    # Process remaining requests
    remaining_count = 0
    while next_request := await rq.fetch_next_request():
        remaining_count += 1
        await rq.mark_request_as_handled(next_request)

    Actor.log.info(f'Processed {remaining_count} remaining requests')
    is_finished = await rq.is_finished()
    assert is_finished is True, f'is_finished={is_finished}'


async def test_empty_rq_behavior(request_queue_apify: RequestQueue) -> None:
    """Test behavior with empty queues."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Test empty queue operations
    is_empty = await rq.is_empty()
    is_finished = await rq.is_finished()
    Actor.log.info(f'Empty queue - is_empty: {is_empty}, is_finished: {is_finished}')
    assert is_empty is True, f'is_empty={is_empty}'
    assert is_finished is True, f'is_finished={is_finished}'

    # Fetch from empty queue
    request = await rq.fetch_next_request()
    Actor.log.info(f'Fetch result from empty queue: {request}')
    assert request is None, f'request={request}'

    # Check metadata for empty queue
    metadata = await rq.get_metadata()
    assert metadata is not None, f'metadata={metadata}'
    Actor.log.info(
        f'Empty queue metadata - Total: {metadata.total_request_count}, '
        f'Handled: {metadata.handled_request_count}, '
        f'Pending: {metadata.pending_request_count}'
    )
    assert metadata.total_request_count == 0, f'metadata.total_request_count={metadata.total_request_count}'
    assert metadata.handled_request_count == 0, f'metadata.handled_request_count={metadata.handled_request_count}'
    assert metadata.pending_request_count == 0, f'metadata.pending_request_count={metadata.pending_request_count}'


async def test_large_batch_operations(request_queue_apify: RequestQueue) -> None:
    """Test handling large batches of requests."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Create a large batch of requests
    large_batch = [f'https://example.com/large/{i}' for i in range(500)]
    Actor.log.info(f'Created batch of {len(large_batch)} requests')

    # Add in batch
    await rq.add_requests(large_batch, batch_size=100, wait_for_all_requests_to_be_added=True)
    Actor.log.info('Large batch add completed')

    # Verify all requests were added
    total_count = await rq.get_total_count()
    assert total_count == 500, f'total_count={total_count}'

    # Process all in chunks to test performance
    processed_count = 0

    while not await rq.is_empty():
        request = await rq.fetch_next_request()

        # The RQ is_empty should ensure we don't get None
        assert request is not None, f'request={request}'

        await rq.mark_request_as_handled(request)
        processed_count += 1

    Actor.log.info(f'Processing completed. Total processed: {processed_count}')
    assert processed_count == 500, f'processed_count={processed_count}'

    is_finished = await rq.is_finished()
    assert is_finished is True, f'is_finished={is_finished}'


async def test_mixed_string_and_request_objects(request_queue_apify: RequestQueue) -> None:
    """Test adding both string URLs and Request objects."""

    rq = request_queue_apify
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
    await rq.add_requests(mixed_batch)
    Actor.log.info('Added mixed batch of strings and Request objects')

    total_count = await rq.get_total_count()
    Actor.log.info(f'Total requests in queue: {total_count}')

    # Fetch and verify all types work
    fetched_requests = []
    while next_request := await rq.fetch_next_request():
        fetched_requests.append(next_request)
        await rq.mark_request_as_handled(next_request)

    assert len(fetched_requests) == 6, f'len(fetched_requests)={len(fetched_requests)}'

    # Find the request object we added
    request_obj_found = None
    for req in fetched_requests:
        if req.user_data and req.user_data.get('type') == 'request_object':
            request_obj_found = req
            break

    assert request_obj_found is not None, f'request_obj_found={request_obj_found}'
    assert request_obj_found.url == 'https://example.com/object1', f'request_obj_found.url={request_obj_found.url}'
    Actor.log.info('Mixed types verified - found request object with user_data')


async def test_persistence_across_operations(request_queue_apify: RequestQueue) -> None:
    """Test that queue state persists across different operations."""

    # Open queue and add some requests
    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add initial batch
    initial_requests = [f'https://example.com/persist/{i}' for i in range(10)]
    await rq.add_requests(initial_requests, wait_for_all_requests_to_be_added=True)
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
    await rq.add_requests(additional_requests, wait_for_all_requests_to_be_added=True)
    Actor.log.info(f'Added additional batch of {len(additional_requests)} requests')

    # Check final state
    total_after_additional = await rq.get_total_count()
    handled_after_additional = await rq.get_handled_count()
    Actor.log.info(
        f'After adding additional batch - Total: {total_after_additional}, Handled: {handled_after_additional}'
    )
    assert total_after_additional == 15, f'total_after_additional={total_after_additional}'
    assert handled_after_additional == 5, f'handled_after_additional={handled_after_additional}'

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
    assert is_finished is True, f'is_finished={is_finished}'
    assert final_total == 15, f'final_total={final_total}'
    assert final_handled == 15, f'final_handled={final_handled}'


async def test_request_deduplication_edge_cases(request_queue_apify: RequestQueue) -> None:
    """Test edge cases in request deduplication."""
    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Test URL normalization and deduplication with expected results
    urls_and_deduplication_expectations: list[tuple[str | Request, bool]] = [
        ('https://example.com/page', False),
        ('https://example.com/page/', True),  # Should be deduplicated (same as first)
        ('https://example.com/page?', True),  # Should be deduplicated (same as first)
        (
            Request.from_url('https://example.com/page#fragment', use_extended_unique_key=True),
            False,
        ),  # Different extended unique key
        ('https://example.com/page?param=1', False),  # Different unique key
    ]
    Actor.log.info(f'Testing deduplication with {len(urls_and_deduplication_expectations)} URLs')

    results = list[bool]()
    for url, expected_duplicate in urls_and_deduplication_expectations:
        result = await rq.add_request(url)
        results.append(result.was_already_present)
        assert result.was_already_present == expected_duplicate, (
            f'url={url}',
            f'expected_duplicate={expected_duplicate}',
            f'actual_was_already_present={result.was_already_present}',
        )

    Actor.log.info(f'was_already_present results: {results}')

    # Calculate expected unique count
    expected_unique_count = sum(1 for _, is_duplicate in urls_and_deduplication_expectations if not is_duplicate)
    Actor.log.info(f'Expected {expected_unique_count} unique requests')

    # Fetch all unique requests
    fetched_urls = list[str]()
    while next_request := await rq.fetch_next_request():
        fetched_urls.append(next_request.url)
        await rq.mark_request_as_handled(next_request)

    # Assert exact expected count
    assert len(fetched_urls) == expected_unique_count, (
        f'len(fetched_urls)={len(fetched_urls)}',
        f'expected_unique_count={expected_unique_count}',
    )
    Actor.log.info(
        f'Added {len(urls_and_deduplication_expectations)} URLs, got {len(fetched_urls)} unique requests as expected'
    )


async def test_request_ordering_with_mixed_operations(request_queue_apify: RequestQueue) -> None:
    """Test request ordering with mixed add/reclaim operations."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Add initial requests
    await rq.add_request('https://example.com/1')
    await rq.add_request('https://example.com/2')
    Actor.log.info('Added initial requests')

    # Fetch one and reclaim to forefront
    request1 = await rq.fetch_next_request()
    assert request1 is not None, f'request1={request1}'
    assert request1.url == 'https://example.com/1', f'request1.url={request1.url}'
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
    assert len(urls_ordered) == 3, f'len(urls_ordered)={len(urls_ordered)}'

    assert urls_ordered[0] == 'https://example.com/priority', f'urls_ordered[0]={urls_ordered[0]}'
    assert urls_ordered[1] == request1.url, (
        f'urls_ordered[1]={urls_ordered[1]}',
        f'request1.url={request1.url}',
    )
    assert urls_ordered[2] == 'https://example.com/2', f'urls_ordered[2]={urls_ordered[2]}'
    Actor.log.info('Request ordering verified successfully')


async def test_finished_state_accuracy(request_queue_apify: RequestQueue) -> None:
    """Test accuracy of is_finished() method in various scenarios."""

    rq = request_queue_apify
    Actor.log.info('Request queue opened')

    # Initially should be finished
    initial_finished = await rq.is_finished()
    Actor.log.info(f'Initial finished state: {initial_finished}')
    assert initial_finished is True, f'initial_finished={initial_finished}'

    # Add requests - should not be finished
    await rq.add_request('https://example.com/test1')
    await rq.add_request('https://example.com/test2')
    after_add_finished = await rq.is_finished()
    Actor.log.info(f'Finished state after adding requests: {after_add_finished}')
    assert after_add_finished is False, f'after_add_finished={after_add_finished}'

    # Fetch but don't handle - should not be finished
    request1 = await rq.fetch_next_request()
    assert request1 is not None, f'request1={request1}'
    after_fetch_finished = await rq.is_finished()
    Actor.log.info(f'Finished state after fetch (not handled): {after_fetch_finished}')
    assert after_fetch_finished is False, f'after_fetch_finished={after_fetch_finished}'

    # Reclaim request - should still not be finished
    await rq.reclaim_request(request1)
    after_reclaim_finished = await rq.is_finished()
    Actor.log.info(f'Finished state after reclaim: {after_reclaim_finished}')
    assert after_reclaim_finished is False, f'after_reclaim_finished={after_reclaim_finished}'

    # Handle all requests - should be finished
    processed_count = 0
    while next_request := await rq.fetch_next_request():
        processed_count += 1
        await rq.mark_request_as_handled(next_request)

    Actor.log.info(f'Processed {processed_count} requests')
    final_finished = await rq.is_finished()
    assert final_finished is True, f'final_finished={final_finished}'


async def test_operations_performance_pattern(request_queue_apify: RequestQueue) -> None:
    """Test a common performance pattern: producer-consumer."""
    Actor.log.info('Request queue opened')
    rq = request_queue_apify

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
    assert processed_count == 20, f'processed_count={processed_count}'

    final_finished = await rq.is_finished()
    assert final_finished is True, f'final_finished={final_finished}'


async def test_request_queue_enhanced_metadata(
    request_queue_apify: RequestQueue,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test metadata tracking.

    Multiple clients scenarios are not guaranteed to give correct results without delay. But at least multiple clients,
    single producer, should be reliable on the producer side."""
    rq = request_queue_apify
    for i in range(1, 10):
        await rq.add_request(Request.from_url(f'http://example.com/{i}'))
        # Reliable information as the API response is enhanced with local metadata estimation.
        assert (await rq.get_metadata()).total_request_count == i

    # Accessed with client created explicitly with `client_key=None` should appear as distinct client
    api_client = apify_client_async.request_queue(request_queue_id=rq.id, client_key=None)
    await api_client.list_head()

    # The presence of another non-producing client should not affect the metadata
    for i in range(10, 20):
        await rq.add_request(Request.from_url(f'http://example.com/{i}'))
        # Reliable information as the API response is enhanced with local metadata estimation.
        assert (await rq.get_metadata()).total_request_count == i


async def test_request_queue_metadata_another_client(
    request_queue_apify: RequestQueue,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test metadata tracking. The delayed metadata should be reliable even when changed by another client."""
    rq = request_queue_apify
    api_client = apify_client_async.request_queue(request_queue_id=rq.id, client_key=None)
    await api_client.add_request(Request.from_url('http://example.com/1').model_dump(by_alias=True, exclude={'id'}))

    # Wait to be sure that the API has updated the global metadata
    await asyncio.sleep(10)

    assert (await rq.get_metadata()).total_request_count == 1


async def test_request_queue_had_multiple_clients(
    request_queue_apify: RequestQueue,
    apify_client_async: ApifyClientAsync,
) -> None:
    """Test that `RequestQueue` correctly detects multiple clients.

    Clients created with different `client_key` should appear as distinct clients."""
    rq = request_queue_apify
    await rq.fetch_next_request()

    # Accessed with client created explicitly with `client_key=None` should appear as distinct client
    api_client = apify_client_async.request_queue(request_queue_id=request_queue_apify.id, client_key=None)
    await api_client.list_head()

    # Check that it is correctly in the RequestQueueClient metadata
    assert (await rq.get_metadata()).had_multiple_clients is True

    # Check that it is correctly in the API
    api_response = await api_client.get()
    assert api_response
    assert api_response['hadMultipleClients'] is True


async def test_request_queue_not_had_multiple_clients(
    request_queue_apify: RequestQueue, apify_client_async: ApifyClientAsync
) -> None:
    """Test that same `RequestQueue` created from Actor does not act as multiple clients."""
    rq = request_queue_apify
    # Two calls to API to create situation where different `client_key` can set `had_multiple_clients` to True
    await rq.fetch_next_request()
    await rq.fetch_next_request()

    # Check that it is correctly in the RequestQueueClient metadata
    assert (await rq.get_metadata()).had_multiple_clients is False

    # Check that it is correctly in the API
    api_client = apify_client_async.request_queue(request_queue_id=rq.id)
    api_response = await api_client.get()
    assert api_response
    assert api_response['hadMultipleClients'] is False


async def test_request_queue_simple_and_full_at_the_same_time(
    apify_token: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test using two variants of the ApifyStorageClient on the same queue resolves to the first client used."""
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    async with Actor:
        rq_simple = await RequestQueue.open(storage_client=ApifyStorageClient(request_queue_access='single'))
        rq_full = await RequestQueue.open(storage_client=ApifyStorageClient(request_queue_access='shared'))
        # Opening same queue again with different ApifyStorageClient will resolve to the first client used.
        assert rq_simple is rq_full
        await rq_simple.drop()


@pytest.mark.parametrize(
    ('access', 'expected_write_count_per_request'),
    [pytest.param('single', 2, id='Simple rq client'), pytest.param('shared', 3, id='Full rq client')],
)
async def test_crawler_run_request_queue_variant_stats(
    *,
    apify_token: str,
    monkeypatch: pytest.MonkeyPatch,
    access: Literal['single', 'shared'],
    expected_write_count_per_request: int,
) -> None:
    """Check the main difference in the simple vs full request queue client - writeCount per request.

    The simple client also has lower readCount, but the costs of read are order of magnitude cheaper than writes, so we
    do test that.
    """
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)
    async with Actor:
        requests = 5
        rq = await RequestQueue.open(storage_client=ApifyStorageClient(request_queue_access=access))
        crawler = BasicCrawler(request_manager=rq)

        @crawler.router.default_handler
        async def default_handler(context: BasicCrawlingContext) -> None:
            context.log.info(f'Processing {context.request.url} ...')

        await crawler.run([Request.from_url(f'https://example.com/{i}') for i in range(requests)])

        # Make sure all requests were handled.
        assert crawler.statistics.state.requests_finished == requests

    # Check the request queue stats
    await asyncio.sleep(10)  # Wait to be sure that metadata are updated

    metadata = cast('ApifyRequestQueueMetadata', await rq.get_metadata())
    Actor.log.info(f'{metadata.stats=}')
    assert metadata.stats.write_count == requests * expected_write_count_per_request
    await rq.drop()


async def test_cache_initialization(apify_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that Apify based simple `RequestQueue` initializes cache correctly to reduce unnecessary API calls."""

    # Create an instance of the Apify request queue on the platform and drop it when the test is finished.
    request_queue_name = generate_unique_resource_name('request_queue')
    monkeypatch.setenv(ApifyEnvVars.TOKEN, apify_token)

    requests = [Request.from_url(f'http://example.com/{i}', handled_at=datetime.now(timezone.utc)) for i in range(10)]

    async with Actor:
        rq = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
        try:
            await rq.add_requests(requests)

            # Check that it is correctly in the API
            await asyncio.sleep(10)  # Wait to be sure that metadata are updated
            metadata = cast('ApifyRequestQueueMetadata', await rq.get_metadata())
            stats_before = metadata.stats
            Actor.log.info(stats_before)

            # Clear service locator cache to simulate creating RQ instance from scratch
            service_locator.storage_instance_manager.clear_cache()

            # Try to enqueue same requests again. It should be deduplicated from local cache created on initialization
            rq = await Actor.open_request_queue(name=request_queue_name, force_cloud=True)
            await rq.add_requests(requests)

            await asyncio.sleep(10)  # Wait to be sure that metadata are updated
            metadata = cast('ApifyRequestQueueMetadata', await rq.get_metadata())
            stats_after = metadata.stats
            Actor.log.info(stats_after)

            # Cache was actually initialized, readCount increased
            assert (stats_after.read_count - stats_before.read_count) == len(requests)
            # Deduplication happened locally, writeCount should be the same
            assert stats_after.write_count == stats_before.write_count

        finally:
            await rq.drop()


async def test_request_queue_has_stats(request_queue_apify: RequestQueue) -> None:
    """Test that Apify based request queue has stats in metadata."""
    rq = request_queue_apify
    add_request_count = 3

    await rq.add_requests([Request.from_url(f'http://example.com/{i}') for i in range(add_request_count)])

    # Wait for stats to become stable
    await asyncio.sleep(10)

    metadata = await rq.get_metadata()

    assert hasattr(metadata, 'stats')
    apify_metadata = cast('ApifyRequestQueueMetadata', metadata)
    assert apify_metadata.stats.write_count == add_request_count


async def test_rq_long_url(request_queue_apify: RequestQueue) -> None:
    rq = request_queue_apify
    request = Request.from_url(
        'https://portal.isoss.gov.cz/irj/portal/anonymous/mvrest?path=/eosm-public-offer&officeLabels=%7B%7D&page=1&pageSize=100000&sortColumn=zdatzvsm&sortOrder=-1',
        use_extended_unique_key=True,
        always_enqueue=True,
    )

    request_id = unique_key_to_request_id(request.unique_key)

    processed_request = await rq.add_request(request)
    assert processed_request.id == request_id

    request_obtained = await rq.fetch_next_request()
    assert request_obtained is not None

    await rq.mark_request_as_handled(request_obtained)

    is_finished = await rq.is_finished()
    assert is_finished


async def test_pre_existing_request_with_user_data(
    request_queue_apify: RequestQueue, apify_client_async: ApifyClientAsync
) -> None:
    """Test that pre-existing requests with user data are fully fetched.

    list_head does not return user data, so we need to test that fetching unknown requests is not relying on it."""
    custom_data = {'key': 'value'}

    rq = request_queue_apify
    request = Request.from_url(
        'https://example.com',
        user_data=custom_data,
    )

    # Add request by a different producer
    rq_client = apify_client_async.request_queue(request_queue_id=rq.id)
    await rq_client.add_request(request.model_dump(by_alias=True))

    # Fetch the request by the client under test
    request_obtained = await rq.fetch_next_request()
    assert request_obtained is not None
    # Test that custom_data is preserved in user_data (custom_data should be subset of obtained user_data)
    assert custom_data.items() <= request_obtained.user_data.items()


async def test_force_cloud(
    apify_client_async: ApifyClientAsync,
    request_queue_apify: RequestQueue,
) -> None:
    request_queue_id = (await request_queue_apify.get_metadata()).id
    request_info = await request_queue_apify.add_request(Request.from_url('http://example.com'))
    assert request_info.id is not None
    request_queue_client = apify_client_async.request_queue(request_queue_id)

    request_queue_details = await request_queue_client.get()
    assert request_queue_details is not None
    assert request_queue_details.get('name') == request_queue_apify.name

    request_queue_request = await request_queue_client.get_request(request_info.id)
    assert request_queue_request is not None
    assert request_queue_request['url'] == 'http://example.com'


async def test_request_queue_is_finished(
    request_queue_apify: RequestQueue,
) -> None:
    await request_queue_apify.add_request(Request.from_url('http://example.com'))
    assert not await request_queue_apify.is_finished()

    request = await request_queue_apify.fetch_next_request()
    assert request is not None
    assert not await request_queue_apify.is_finished(), (
        'RequestQueue should not be finished unless the request is marked as handled.'
    )

    await request_queue_apify.mark_request_as_handled(request)
    assert await request_queue_apify.is_finished()


async def test_request_queue_deduplication_unprocessed_requests(
    request_queue_apify: RequestQueue,
) -> None:
    """Test that the deduplication does not add unprocessed requests to the cache.

    In this test the first call is "hardcoded" to fail, even on all retries, so it never even sends the API request and
    thus has no chance of increasing the `writeCount`. The second call can increase the `writeCount` only if it is not
    cached, as cached requests do not make the call (tested in other tests). So this means the `unprocessedRequests`
    request was intentionally not cached."""
    logging.getLogger('apify.storage_clients._apify._request_queue_client').setLevel(logging.DEBUG)

    await asyncio.sleep(10)  # Wait to be sure that metadata are updated

    # Get raw client, because stats are not exposed in `RequestQueue` class, but are available in raw client
    rq_client = Actor.apify_client.request_queue(request_queue_id=request_queue_apify.id)
    _rq = await rq_client.get()
    assert _rq
    stats_before = _rq.get('stats', {})
    Actor.log.info(stats_before)

    def return_unprocessed_requests(requests: list[dict], *_: Any, **__: Any) -> dict[str, list[dict]]:
        """Simulate API returning unprocessed requests."""
        return {
            'processedRequests': [],
            'unprocessedRequests': [
                {'url': request['url'], 'uniqueKey': request['uniqueKey'], 'method': request['method']}
                for request in requests
            ],
        }

    with mock.patch(
        'apify_client.clients.resource_clients.request_queue.RequestQueueClientAsync.batch_add_requests',
        side_effect=return_unprocessed_requests,
    ):
        # Simulate failed API call for adding requests. Request was not processed and should not be cached.
        await request_queue_apify.add_requests(['http://example.com/1'])

    # This will succeed.
    await request_queue_apify.add_requests(['http://example.com/1'])

    await asyncio.sleep(10)  # Wait to be sure that metadata are updated
    _rq = await rq_client.get()
    assert _rq
    stats_after = _rq.get('stats', {})
    Actor.log.info(stats_after)

    assert (stats_after['writeCount'] - stats_before['writeCount']) == 1
