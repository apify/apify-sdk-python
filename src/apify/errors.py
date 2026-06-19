"""`apify.errors` re-exports the Apify API client's error hierarchy.

Callers get a single import location for every error raised by an operation that talks to the Apify API. The SDK
raises these client exceptions as-is and does not wrap them in its own types. See
https://docs.apify.com/api/client/python for the full client error reference.
"""

from __future__ import annotations

from apify_client.errors import (
    ApifyApiError,
    ApifyClientError,
    ConflictError,
    ForbiddenError,
    InvalidRequestError,
    InvalidResponseBodyError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnauthorizedError,
)

__all__ = [
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
