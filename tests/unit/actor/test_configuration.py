from pathlib import Path

import pytest

from crawlee import service_locator
from crawlee.configuration import Configuration as CrawleeConfiguration
from crawlee.crawlers import BasicCrawler
from crawlee.errors import ServiceConflictError

from apify import Actor
from apify import Configuration as ApifyConfiguration


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


def test_apify_configuration_is_always_used() -> None:
    """Set Crawlee Configuration in service_locator and verify that Apify Configuration is returned."""
    max_used_cpu_ratio = 0.123456  # Some unique value to verify configuration
    service_locator.set_configuration(CrawleeConfiguration(max_used_cpu_ratio=max_used_cpu_ratio))

    returned_config = service_locator.get_configuration()
    assert returned_config.max_used_cpu_ratio == max_used_cpu_ratio
    assert isinstance(returned_config, ApifyConfiguration)


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

    returned_config = service_locator.get_configuration()
    assert returned_config is not crawlee_config
    assert isinstance(returned_config, ApifyConfiguration)
    # Make sure the Crawlee Configuration was used to create returned Apify Configuration
    assert returned_config.max_used_cpu_ratio == max_used_cpu_ratio


async def test_existing_apify_config_throws_error_when_set_in_actor() -> None:
    """Test that passing explicit configuration to actor after service locator configuration was already set,
    raises exception."""
    service_locator.set_configuration(ApifyConfiguration())
    with pytest.raises(ServiceConflictError):
        async with Actor(configuration=ApifyConfiguration()):
            pass


async def test_setting_config_after_actor_raises_exception() -> None:
    """Test that passing setting configuration in service locator after actor wa created raises an exception."""
    async with Actor():
        with pytest.raises(ServiceConflictError):
            service_locator.set_configuration(ApifyConfiguration())


async def test_actor_using_input_configuration() -> None:
    """Test that passing setting configuration in service locator after actor wa created raises an exception."""
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
        crawler = BasicCrawler()

    assert service_locator.get_configuration() is crawler._service_locator.get_configuration()


async def test_crawlers_own_configuration() -> None:
    """Test that crawlers can use own configurations without crashing."""
    config_actor = ApifyConfiguration()
    apify_crawler_1 = ApifyConfiguration()
    apify_crawler_2 = ApifyConfiguration()

    async with Actor(configuration=config_actor):
        crawler_1 = BasicCrawler(configuration=apify_crawler_1)
        crawler_2 = BasicCrawler(configuration=apify_crawler_2)

    assert service_locator.get_configuration() is config_actor
    assert crawler_1._service_locator.get_configuration() is apify_crawler_1
    assert crawler_2._service_locator.get_configuration() is apify_crawler_2


async def test_crawler_global_configuration() -> None:
    """Test that crawler and Actor use explicit service_locator based configuration unless explicit configuration
    was passed to them."""
    config_global = ApifyConfiguration()
    service_locator.set_configuration(config_global)

    async with Actor():
        crawler = BasicCrawler()

    assert service_locator.get_configuration() is config_global
    assert crawler._service_locator.get_configuration() is config_global


async def test_storage_retrieved_is_different_with_different_config(tmp_path: Path) -> None:
    """Test that retrieving storage depends on used configuration."""
    dir_1 = tmp_path / 'dir_1'
    dir_2 = tmp_path / 'dir_2'
    config_actor = ApifyConfiguration()
    config_actor.storage_dir = str(dir_1)
    apify_crawler = ApifyConfiguration()
    apify_crawler.storage_dir = str(dir_2)

    async with Actor(configuration=config_actor):
        actor_kvs = await Actor.open_key_value_store()
        crawler = BasicCrawler(configuration=apify_crawler)
        crawler_kvs = await crawler.get_key_value_store()

    assert actor_kvs is not crawler_kvs


async def test_storage_retrieved_is_same_with_equivalent_config() -> None:
    """Test that retrieving storage depends on used configuration. If two same configuration(even if they are different
    instances) are used it returns same storage."""
    config_actor = ApifyConfiguration()
    apify_crawler = ApifyConfiguration()

    async with Actor(configuration=config_actor):
        actor_kvs = await Actor.open_key_value_store()
        crawler = BasicCrawler(configuration=apify_crawler)
        crawler_kvs = await crawler.get_key_value_store()

    assert actor_kvs is crawler_kvs


async def test_storage_retrieved_is_same_with_same_config() -> None:
    """Test that retrieving storage is same if same configuration is used."""
    async with Actor():
        actor_kvs = await Actor.open_key_value_store()
        crawler = BasicCrawler()
        crawler_kvs = await crawler.get_key_value_store()

    assert actor_kvs is crawler_kvs


async def test_crawler_uses_apify_config() -> None:
    """Test that crawler is using ApifyConfiguration in SDK context."""
    crawler = BasicCrawler()
    assert isinstance(crawler._service_locator.get_configuration(), ApifyConfiguration)
