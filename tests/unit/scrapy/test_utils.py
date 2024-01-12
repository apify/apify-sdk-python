from __future__ import annotations

import pytest

from apify.scrapy import get_basic_auth_header


@pytest.mark.parametrize(
    ('username', 'password', 'expected_auth_header'),
    [
        ('username', 'password', b'Basic dXNlcm5hbWU6cGFzc3dvcmQ='),
        ('john_smith', 'secret_password_123', b'Basic am9obl9zbWl0aDpzZWNyZXRfcGFzc3dvcmRfMTIz'),
    ],
)
def test__get_basic_auth_header(
    username: str,
    password: str,
    expected_auth_header: bytes,
) -> None:
    auth_header = get_basic_auth_header(username, password)
    assert auth_header == expected_auth_header


def test__to_apify_request() -> None:
    ...


def test__to_scrapy_request() -> None:
    ...
