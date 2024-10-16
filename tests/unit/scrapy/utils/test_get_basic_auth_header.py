from __future__ import annotations

from dataclasses import dataclass

import pytest

from apify.scrapy import get_basic_auth_header


@dataclass(frozen=True)
class ItemTestCase:
    username: str
    password: str
    expected_auth_header: bytes


@pytest.mark.parametrize(
    'tc',
    [
        ItemTestCase('username', 'password', b'Basic dXNlcm5hbWU6cGFzc3dvcmQ='),
        ItemTestCase('john_smith', 'secret_password_123', b'Basic am9obl9zbWl0aDpzZWNyZXRfcGFzc3dvcmRfMTIz'),
    ],
    ids=['simple_username_password', 'complex_username_password'],
)
def test_basic_auth_header_generation(tc: ItemTestCase) -> None:
    auth_header = get_basic_auth_header(tc.username, tc.password)
    assert auth_header == tc.expected_auth_header
