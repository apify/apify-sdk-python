from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from itertools import islice
from logging import getLogger
from typing import TYPE_CHECKING

from apify_client import ApifyClientAsync
from apify_shared.consts import ActorEventTypes
from crawlee import Request, service_locator
from crawlee.storage_clients._memory import MemoryRequestQueueClient
from crawlee.storage_clients.models import KeyValueStoreMetadata, RequestQueueMetadata

if TYPE_CHECKING:
    from apify_client.clients import KeyValueStoreClientAsync

    from apify import Configuration

logger = getLogger(__name__)


class MemoryRequestQueueClientWithPersistance(MemoryRequestQueueClient):
    """RequestQueue implementation that uses `MemoryRequestQueueClient` with limited persistence capability.

    Advantages:
    - Fast in-memory operations.
    - Cheap RequestQueue as it uses platform KVS only for persistence per large chunks.

    Drawbacks:
    - Uses memory of the crawler.
    - Cannot be used with multiple consumers.
    - Migration is not guaranteed to work for extremely large RequestQueue due to limited migration time window.

    Ideal use case:
    - Isolated crawlers with limited lifespan. (One RQ consumer, less than ???k requests)

    If the `MemoryRequestQueueClientWithPersistance` is not sufficient for your use case, consider using request queue for adults
    `ApifyRequestQueueClient` instead.
    """

    _PERSISTANCE_NAME_PREFIX = '_persisted_rq_'
    _PERSISTANCE_CHUNK_SIZE = 10000

    def __init__(
        self,
        *,
        metadata: RequestQueueMetadata,
        api_client: KeyValueStoreClientAsync,
    ) -> None:
        super().__init__(metadata=metadata)
        logger.info(
            'Using `MemoryRequestQueueClientWithPersistance`. Consider using `ApifyRequestQueueClient` for more complex crawlers.'
        )

        self._api_client = api_client
        """The Apify request queue client for API operations."""

        # Register persistence listener
        event_manager = service_locator.get_event_manager()
        event_manager.on(event=ActorEventTypes.ABORTING, listener=self.to_kvs)
        event_manager.on(event=ActorEventTypes.MIGRATING, listener=self.to_kvs)

    @classmethod
    async def open(
        cls,
        *,
        id: str | None,
        name: str | None,
        configuration: Configuration,
    ) -> MemoryRequestQueueClientWithPersistance:
        # COPYPASTA from ApifyRequestQueueClient.open TODO: Refactor if team agrees on this idea.
        token = configuration.token
        if not token:
            raise ValueError(f'Apify storage client requires a valid token in Configuration (token={token}).')

        api_url = configuration.api_base_url
        if not api_url:
            raise ValueError(f'Apify storage client requires a valid API URL in Configuration (api_url={api_url}).')

        api_public_base_url = configuration.api_public_base_url
        if not api_public_base_url:
            raise ValueError(
                'Apify storage client requires a valid API public base URL in Configuration '
                f'(api_public_base_url={api_public_base_url}).'
            )

        # Create Apify client with the provided token and API URL.
        apify_client_async = ApifyClientAsync(
            token=token,
            api_url=api_url,
            max_retries=8,
            min_delay_between_retries_millis=500,
            timeout_secs=360,
        )
        apify_kvss_client = apify_client_async.key_value_stores()

        # If both id and name are provided, raise an error.
        if id and name:
            raise ValueError('Only one of "id" or "name" can be specified, not both.')

        # If id is provided, get the storage by ID.
        if id and name is None:
            apify_kvs_client = apify_client_async.key_value_store(key_value_store_id=id)

        # If name is provided, get or create the storage by name.
        if name and id is None:
            id = KeyValueStoreMetadata.model_validate(
                await apify_kvss_client.get_or_create(name=name),
            ).id
            apify_kvs_client = apify_client_async.key_value_store(key_value_store_id=id)

        # If both id and name are None, try to get the default storage ID from environment variables.
        if id is None and name is None:
            apify_kvs_client = apify_client_async.key_value_store(
                key_value_store_id=configuration.default_key_value_store_id
            )

        # Fetch its metadata.
        metadata = await apify_kvs_client.get()

        # If metadata is None, it means the storage does not exist, so we create it.
        if metadata is None:
            id = KeyValueStoreMetadata.model_validate(
                await apify_kvss_client.get_or_create(),
            ).id
            apify_kvs_client = apify_client_async.key_value_store(key_value_store_id=id)

        # Verify that the storage exists by fetching its metadata again.
        metadata = await apify_kvs_client.get()
        if metadata is None:
            raise ValueError(f'Opening kvs with id={id} and name={name} failed.')


        local_rq = cls(
            metadata=RequestQueueMetadata(**metadata, had_multiple_clients=False, handled_request_count=0, pending_request_count=0,  total_request_count=0),
            api_client=apify_kvs_client,
        )
        await local_rq.from_kvs()
        return local_rq

    @staticmethod
    def _get_batches(source: Iterable, batch_size: int) -> list:
        """Yield successive n-sized chunks from source.

        itertools.batched in Python3.12
        """
        for i in range(0, len(source), batch_size):
            yield list(islice(source, i, (i + batch_size)))

    async def _persist_requests(self, requests: list[Request], request_category: str) -> list[list]:
        batch_number = 1

        def json_serial(obj):
            """JSON serializer for objects not serializable by default json code"""
            from datetime import date, datetime
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError('Type %s not serializable' % type(obj))


        for request_batch in self._get_batches(requests, self._PERSISTANCE_CHUNK_SIZE):
            request_batch_json = json.dumps([request.model_dump(by_alias=True) for request in request_batch], default=json_serial)
            await self._api_client.set_record(
                f'{self._PERSISTANCE_NAME_PREFIX}_{request_category}_{batch_number}', request_batch_json
            )
            batch_number += 1

    async def to_kvs(self) -> None:
        """Persist to Apify KVS."""
        logger.info('Persisting RequestQueue to KVS.')
        await self._persist_requests(self._pending_requests, 'pending')
        await self._persist_requests(self._handled_requests.values(), 'handled')

    async def from_kvs(self) -> None:
        """Load from Apify KVS."""
        logger.info('Load RequestQueue from KVS.')
        # Just for POC. Organization of stored RQ can be improved later
        persisted_batches = await self._api_client.list_keys(prefix=self._PERSISTANCE_NAME_PREFIX)
        if persisted_batches['count'] == 0:
            # No persisted request batches found, nothing to load.
            return
        persisted_batches_names = [item['key'] for item in  persisted_batches['items']]

        for batche_name in sorted(persisted_batches_names):
            request_batch = await self._api_client.get_record(batche_name)
            assert request_batch is not None
            for raw_request in json.loads(request_batch['value']):
                request = Request.model_validate(raw_request)
                if 'handled' in batche_name:
                    self._handled_requests[request.url] = request
                else:
                    self._pending_requests.append(request)
                self._requests_by_id[request.id] = request
                self._requests_by_unique_key[request.unique_key] = request


async def main():
    from apify import Configuration
    c = Configuration(token='...')
    rq_client = await MemoryRequestQueueClientWithPersistance.open(
        id=None, name='blbalblo', configuration=c
    )
    requests = [Request.from_url('http://www.example.com'), Request.from_url('http://www.example2.com')]
    await rq_client.add_batch_of_requests(requests)
    r = await rq_client.fetch_next_request()
    await rq_client.mark_request_as_handled(r)
    await rq_client.to_kvs()
    await rq_client.from_kvs()

if __name__ == '__main__':
    asyncio.run(main())
