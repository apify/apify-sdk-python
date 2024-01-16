from __future__ import annotations

from dataclasses import dataclass

import pytest

from apify.scrapy import get_basic_auth_header


@dataclass(frozen=True)
class TestCase:
    username: str
    password: str
    expected_auth_header: bytes


test_cases = [
    TestCase('username', 'password', b'Basic dXNlcm5hbWU6cGFzc3dvcmQ='),
    TestCase('john_smith', 'secret_password_123', b'Basic am9obl9zbWl0aDpzZWNyZXRfcGFzc3dvcmRfMTIz'),
]


@pytest.mark.parametrize('tc', test_cases)
def test__get_basic_auth_header(tc: TestCase) -> None:
    auth_header = get_basic_auth_header(tc.username, tc.password)
    assert auth_header == tc.expected_auth_header
