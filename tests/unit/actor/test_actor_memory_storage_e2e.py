from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import pytest
from apify_shared.consts import ApifyEnvVars
from crawlee.storage_client_manager import StorageClientManager

from apify import Actor


@pytest.mark.parametrize('purge_on_start', [True, False])
async def test_actor_memory_storage_client_key_value_store_e2e(
    monkeypatch: pytest.MonkeyPatch,
    purge_on_start: bool,  # noqa: FBT001
    reset_default_instances: Callable[[], None],
) -> None:
    """This test simulates two clean runs using memory storage.
    The second run attempts to access data created by the first one.
    We run 2 configurations with different `purge_on_start`."""
    # Configure purging env var
    monkeypatch.setenv(ApifyEnvVars.PURGE_ON_START, f'{int(purge_on_start)}')
    # Store old storage client so we have the object reference for comparison
    old_client = StorageClientManager.get_storage_client()
    async with Actor:
        old_default_kvs = await Actor.open_key_value_store()
        old_non_default_kvs = await Actor.open_key_value_store(name='non-default')
        # Create data in default and non-default key-value store
        await old_default_kvs.set_value('test', 'default value')
        await old_non_default_kvs.set_value('test', 'non-default value')

    # We simulate another clean run, we expect the memory storage to read from the local data directory
    # Default storages are purged based on purge_on_start parameter.
    reset_default_instances()

    async with Actor:
        # Check if we're using a different memory storage instance
        assert old_client is not StorageClientManager.get_storage_client()
        default_kvs = await Actor.open_key_value_store()
        assert default_kvs is not old_default_kvs
        non_default_kvs = await Actor.open_key_value_store(name='non-default')
        assert non_default_kvs is not old_non_default_kvs
        default_value = await default_kvs.get_value('test')
        non_default_value = await non_default_kvs.get_value('test')
        if purge_on_start:
            assert default_value is None
        else:
            assert default_value == 'default value'
        assert non_default_value == 'non-default value'


@pytest.mark.parametrize('purge_on_start', [True, False])
async def test_actor_memory_storage_client_request_queue_e2e(
    monkeypatch: pytest.MonkeyPatch,
    purge_on_start: bool,  # noqa: FBT001
    reset_default_instances: Callable[[], None],
) -> None:
    """This test simulates two clean runs using memory storage.
    The second run attempts to access data created by the first one.
    We run 2 configurations with different `purge_on_start`."""
    # Configure purging env var
    monkeypatch.setenv(ApifyEnvVars.PURGE_ON_START, f'{int(purge_on_start)}')
    async with Actor:
        # Add some requests to the default queue
        default_queue = await Actor.open_request_queue()
        for i in range(6):
            request_url = f'http://example.com/{i}'
            forefront = i % 3 == 1
            was_handled = i % 3 == 2
            await default_queue.add_request(
                {
                    'uniqueKey': str(i),
                    'url': request_url,
                    'handledAt': datetime.now(timezone.utc) if was_handled else None,
                },
                forefront=forefront,
            )

    # We simulate another clean run, we expect the memory storage to read from the local data directory
    # Default storages are purged based on purge_on_start parameter.
    reset_default_instances()

    async with Actor:
        # Add some more requests to the default queue
        default_queue = await Actor.open_request_queue()
        for i in range(6, 12):
            request_url = f'http://example.com/{i}'
            forefront = i % 3 == 1
            was_handled = i % 3 == 2
            await default_queue.add_request(
                {
                    'uniqueKey': str(i),
                    'url': request_url,
                    'handledAt': datetime.now(timezone.utc) if was_handled else None,
                },
                forefront=forefront,
            )

        queue_info = await default_queue.get_info()
        assert queue_info is not None

        # If the queue was purged between the runs, only the requests from the second run should be present, in the right order
        if purge_on_start:
            assert queue_info.get('totalRequestCount') == 6
            assert queue_info.get('handledRequestCount') == 2

            expected_pending_request_order = [10, 7, 6, 9]
            for request_number in expected_pending_request_order:
                next_request = await default_queue.fetch_next_request()
                assert next_request is not None
                assert next_request.get('uniqueKey') == f'{request_number}'
                assert next_request.get('url') == f'http://example.com/{request_number}'

            next_request = await default_queue.fetch_next_request()
            assert next_request is None
        # If the queue was NOT purged between the runs, all the requests should be in the queue in the right order
        else:
            assert queue_info.get('totalRequestCount') == 12
            assert queue_info.get('handledRequestCount') == 4

            expected_pending_request_order = [10, 7, 4, 1, 0, 3, 6, 9]
            for request_number in expected_pending_request_order:
                next_request = await default_queue.fetch_next_request()
                assert next_request is not None
                assert next_request.get('uniqueKey') == f'{request_number}'
                assert next_request.get('url') == f'http://example.com/{request_number}'

            next_request = await default_queue.fetch_next_request()
            assert next_request is None
