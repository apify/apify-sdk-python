from pathlib import Path

import pytest

from crawlee import Request, service_locator
from crawlee._types import BasicCrawlingContext
from crawlee.configuration import Configuration as CrawleeConfiguration
from crawlee.crawlers import BasicCrawler
from crawlee.errors import ServiceConflictError

from apify import Actor
from apify import Configuration as ApifyConfiguration
from apify.storage_clients._smart_apify._storage_client import SmartApifyStorageClient


@pytest.mark.parametrize(
    ('is_at_home', 'disable_browser_sandbox_in', 'disable_browser_sandbox_out'),
    [
        (False, False, False),
        (False, True, True),
        (True, False, True),
        (True, True, True),
    ],
)
def test_disable_browser_sandbox(
    *, is_at_home: bool, disable_browser_sandbox_in: bool, disable_browser_sandbox_out: bool
) -> None:
    assert (
        ApifyConfiguration(
            is_at_home=is_at_home, disable_browser_sandbox=disable_browser_sandbox_in
        ).disable_browser_sandbox
        == disable_browser_sandbox_out
    )


async def test_existing_apify_config_respected_by_actor() -> None:
    """Set Apify Configuration in service_locator and verify that Actor respects it."""
    max_used_cpu_ratio = 0.123456  # Some unique value to verify configuration
    apify_config = ApifyConfiguration(max_used_cpu_ratio=max_used_cpu_ratio)
    service_locator.set_configuration(apify_config)
    async with Actor:
        pass

    returned_config = service_locator.get_configuration()
    assert returned_config is apify_config


async def test_existing_crawlee_config_respected_by_actor() -> None:
    """Set Crawlee Configuration in service_locator and verify that Actor respects it."""
    max_used_cpu_ratio = 0.123456  # Some unique value to verify configuration
    crawlee_config = CrawleeConfiguration(max_used_cpu_ratio=max_used_cpu_ratio)
    service_locator.set_configuration(crawlee_config)
    async with Actor:
        pass

    assert Actor.configuration is not crawlee_config
    assert isinstance(Actor.configuration, ApifyConfiguration)
    # Make sure the Crawlee Configuration was used to create ApifyConfiguration in Actor
    assert Actor.configuration.max_used_cpu_ratio == max_used_cpu_ratio


async def test_existing_apify_config_throws_error_when_set_in_actor() -> None:
    """Test that passing explicit configuration to actor after service locator configuration was already set,
    raises exception."""
    service_locator.set_configuration(ApifyConfiguration())
    with pytest.raises(ServiceConflictError):
        async with Actor(configuration=ApifyConfiguration()):
            pass


async def test_setting_config_after_actor_raises_exception() -> None:
    """Test that setting configuration in service locator after actor was created raises an exception."""
    async with Actor():
        with pytest.raises(ServiceConflictError):
            service_locator.set_configuration(ApifyConfiguration())


async def test_actor_using_input_configuration() -> None:
    """Test that setting configuration in service locator after actor was created raises an exception."""
    apify_config = ApifyConfiguration()
    async with Actor(configuration=apify_config):
        pass

    assert service_locator.get_configuration() is apify_config


async def test_crawler_implicit_configuration_through_actor() -> None:
    """Test that crawler uses Actor configuration unless explicit configuration was passed to it."""
    apify_config = ApifyConfiguration()
    async with Actor(configuration=apify_config):
        crawler = BasicCrawler()

    assert crawler._service_locator.get_configuration() is apify_config
    assert service_locator.get_configuration() is apify_config


async def test_crawler_implicit_configuration() -> None:
    """Test that crawler and Actor use implicit service_locator based configuration unless explicit configuration
    was passed to them."""
    async with Actor():
        assert Actor.configuration is service_locator.get_configuration()
        crawler = BasicCrawler()

    assert Actor.configuration is service_locator.get_configuration()
    assert Actor.configuration is crawler._service_locator.get_configuration()


async def test_crawler_implicit_local_storage() -> None:
    """Test that crawler and Actor use implicit ApifyFileSystemStorageClient."""
    async with Actor():
        crawler = BasicCrawler()

    assert isinstance(service_locator.get_storage_client(), SmartApifyStorageClient)
    assert isinstance(crawler._service_locator.get_storage_client(), SmartApifyStorageClient)


async def test_crawlers_own_configuration(tmp_path: Path) -> None:
    """Test that crawlers can use own configurations without crashing."""
    config_actor = ApifyConfiguration()
    dir_1 = tmp_path / 'dir_1'
    dir_2 = tmp_path / 'dir_2'
    config_crawler_1 = ApifyConfiguration()
    config_actor.storage_dir = str(dir_1)
    config_crawler_2 = ApifyConfiguration()
    config_crawler_2.storage_dir = str(dir_2)

    async with Actor(configuration=config_actor):

        async def request_handler(context: BasicCrawlingContext) -> None:
            Actor.log.info(f'Processing: {context.request.url}')

        crawler_1 = BasicCrawler(configuration=config_crawler_1, request_handler=request_handler)
        crawler_2 = BasicCrawler(configuration=config_crawler_2, request_handler=request_handler)
        await crawler_1.add_requests([Request.from_url(url='http://example.com/1')])
        await crawler_2.add_requests(
            [Request.from_url(url='http://example.com/2'), Request.from_url(url='http://example.com/3')]
        )

        await crawler_1.run()
        await crawler_2.run()

    assert service_locator.get_configuration() is config_actor
    assert crawler_1._service_locator.get_configuration() is config_crawler_1
    assert crawler_2._service_locator.get_configuration() is config_crawler_2

    assert crawler_1.statistics.state.requests_total == 1
    assert crawler_2.statistics.state.requests_total == 2


async def test_crawler_global_configuration() -> None:
    """Test that crawler and Actor use service_locator based configuration unless explicit configuration
    was passed to them."""
    config_global = ApifyConfiguration()
    service_locator.set_configuration(config_global)

    async with Actor():
        crawler = BasicCrawler()

    assert service_locator.get_configuration() is config_global
    assert crawler._service_locator.get_configuration() is config_global


async def test_crawler_uses_implicit_apify_config() -> None:
    """Test that Actor is using implicit ApifyConfiguration in Actor context."""
    async with Actor:
        assert isinstance(Actor.configuration, ApifyConfiguration)


async def test_storages_retrieved_is_different_with_different_config(tmp_path: Path) -> None:
    """Test that retrieving storage depends on used configuration."""
    dir_1 = tmp_path / 'dir_1'
    dir_2 = tmp_path / 'dir_2'
    config_actor = ApifyConfiguration()
    config_actor.storage_dir = str(dir_1)
    config_crawler = ApifyConfiguration()
    config_crawler.storage_dir = str(dir_2)

    async with Actor(configuration=config_actor):
        actor_kvs = await Actor.open_key_value_store()
        actor_dataset = await Actor.open_dataset()
        actor_rq = await Actor.open_request_queue()

        crawler = BasicCrawler(configuration=config_crawler)
        crawler_kvs = await crawler.get_key_value_store()
        crawler_dataset = await crawler.get_dataset()
        crawler_rq = await crawler.get_request_manager()

    assert actor_kvs is not crawler_kvs
    assert actor_dataset is not crawler_dataset
    assert actor_rq is not crawler_rq


async def test_storages_retrieved_is_same_with_equivalent_config() -> None:
    """Test that retrieving storage depends on used configuration. If two equivalent configuration(even if they are
    different instances) are used it returns same storage."""
    config_actor = ApifyConfiguration()
    config_crawler = ApifyConfiguration()

    async with Actor(configuration=config_actor):
        actor_kvs = await Actor.open_key_value_store()
        actor_dataset = await Actor.open_dataset()
        actor_rq = await Actor.open_request_queue()

        crawler = BasicCrawler(configuration=config_crawler)
        crawler_kvs = await crawler.get_key_value_store()
        crawler_dataset = await crawler.get_dataset()
        crawler_rq = await crawler.get_request_manager()

    assert actor_kvs is crawler_kvs
    assert actor_dataset is crawler_dataset
    assert actor_rq is crawler_rq


async def test_storages_retrieved_is_same_with_same_config() -> None:
    """Test that retrieving storage is same if same configuration is used."""
    async with Actor():
        actor_kvs = await Actor.open_key_value_store()
        actor_dataset = await Actor.open_dataset()
        actor_rq = await Actor.open_request_queue()

        crawler = BasicCrawler()
        crawler_kvs = await crawler.get_key_value_store()
        crawler_dataset = await crawler.get_dataset()
        crawler_rq = await crawler.get_request_manager()

    assert actor_kvs is crawler_kvs
    assert actor_dataset is crawler_dataset
    assert actor_rq is crawler_rq


def test_apify_configuration_is_always_used(caplog: pytest.LogCaptureFixture) -> None:
    """Set Crawlee Configuration in Actor and verify that Apify Configuration is used with warning."""
    max_used_cpu_ratio = 0.123456  # Some unique value to verify configuration

    service_locator.set_configuration(CrawleeConfiguration(max_used_cpu_ratio=max_used_cpu_ratio))

    assert Actor.configuration.max_used_cpu_ratio == max_used_cpu_ratio
    assert isinstance(Actor.configuration, ApifyConfiguration)
    assert (
        'Non Apify Configuration is set in the `service_locator` in the SDK context. '
        'It is recommended to set `apify.Configuration` explicitly as early as possible by using '
        'service_locator.set_configuration'
    ) in caplog.messages
