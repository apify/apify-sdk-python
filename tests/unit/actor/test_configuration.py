import pytest

from crawlee.configuration import Configuration as CrawleeConfiguration

from apify import Configuration as ApifyConfiguration
from apify._configuration import service_locator


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
    # Some value to verify
    max_used_cpu_ratio = 0.123456
    service_locator.set_configuration(CrawleeConfiguration(max_used_cpu_ratio=max_used_cpu_ratio))

    returned_config = service_locator.get_configuration()
    assert returned_config.max_used_cpu_ratio == max_used_cpu_ratio
    assert isinstance(returned_config, ApifyConfiguration)
