import asyncio
from http.server import HTTPServer
from logging import getLogger
from typing import Iterator
from unittest.mock import Mock, AsyncMock

import pytest
from crawlee import service_locator
from crawlee._types import BasicCrawlingContext, ConcurrencySettings
from crawlee.crawlers import BasicCrawler
from crawlee.storages import RequestQueue

from apify import Configuration
from apify.storage_clients import ApifyStorageClient



async def test_crawlee_api_usage_when_rq_empty_but_not_finished(apify_token: str, httpserver):
    """Test that crawler is not bombing the API when only in progress requests are present.

    Scenario: The request queue is already empty but the crawler is working on some time-consuming in progress requests.
    It should not try to spawn more tasks and bomb the API with requests for more work since the "single" client knows
    there are no more requests to fetch.

    No matter how long time the crawler was running, it should not try to fetch more requests since the "single"
    client knows there are no more requests to fetch. Number of calls should be at max 4:
    - One for initial check cache init
    - One for initial check if the Crawler is finished (checks the RQ)
    - One for fetching head
    - One for fetching the request
    """

    max_expected_calls = 4

    service_locator.set_configuration(Configuration(token=apify_token))
    request_queue = await RequestQueue.open(storage_client=ApifyStorageClient(request_queue_access="single"))

    crawler = BasicCrawler(
        http_client=AsyncMock(),
        request_manager=request_queue,
        concurrency_settings=ConcurrencySettings(min_concurrency=1, max_concurrency=10, desired_concurrency=1),
    )

    @crawler.router.default_handler
    async def request_handler(_: BasicCrawlingContext):
        # Give the crawler opportunity to scale up.
        await asyncio.sleep(5)

    await crawler.run(["https://crawlee.dev/"])

    # Wait for metadata to stabilize.
    await asyncio.sleep(5)
    metadata = await request_queue._client.get_metadata()
    assert metadata.stats.head_item_read_count<=max_expected_calls

