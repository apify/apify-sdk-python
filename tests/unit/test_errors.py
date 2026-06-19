from __future__ import annotations

import apify_client.errors as client_errors

import apify.errors as sdk_errors


def test_client_errors_are_re_exported() -> None:
    """`apify.errors` re-exports the API client error hierarchy so callers have a single import location."""
    names = [
        'ApifyApiError',
        'ApifyClientError',
        'ConflictError',
        'ForbiddenError',
        'InvalidRequestError',
        'InvalidResponseBodyError',
        'NotFoundError',
        'RateLimitError',
        'ServerError',
        'UnauthorizedError',
    ]
    assert set(sdk_errors.__all__) == set(names)
    for name in names:
        assert getattr(sdk_errors, name) is getattr(client_errors, name)
