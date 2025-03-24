import pytest

from apify import Configuration


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
        Configuration(is_at_home=is_at_home, disable_browser_sandbox=disable_browser_sandbox_in).disable_browser_sandbox
        == disable_browser_sandbox_out
    )
