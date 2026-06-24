from __future__ import annotations

import asyncio
import re
from base64 import b64encode
from hashlib import sha256
from typing import TYPE_CHECKING

from crawlee._utils.crypto import compute_short_hash
from crawlee.storage_clients.models import ProcessedRequest, UnprocessedRequest

from apify import Request

if TYPE_CHECKING:
    from collections.abc import Iterable

    from apify_client._models import HeadRequest, LockedHeadRequest
    from apify_client._models import Request as ClientRequest
    from crawlee.storage_clients.models import AddRequestsResponse

    from apify import Configuration


def unique_key_to_request_id(unique_key: str, *, request_id_length: int = 15) -> str:
    """Generate a deterministic request ID based on a unique key.

    Args:
        unique_key: The unique key to convert into a request ID.
        request_id_length: The length of the request ID.

    Returns:
        A URL-safe, truncated request ID based on the unique key.
    """
    # Encode the unique key and compute its SHA-256 hash
    hashed_key = sha256(unique_key.encode('utf-8')).digest()

    # Encode the hash in base64 and decode it to get a string
    base64_encoded = b64encode(hashed_key).decode('utf-8')

    # Remove characters that are not URL-safe ('+', '/', or '=')
    url_safe_key = re.sub(r'(\+|\/|=)', '', base64_encoded)

    # Truncate the key to the desired length
    return url_safe_key[:request_id_length]


def hash_api_base_url_and_token(configuration: Configuration) -> str:
    """Hash configuration.api_public_base_url and configuration.token in deterministic way."""
    if configuration.api_public_base_url is None or configuration.token is None:
        raise ValueError("'Configuration.api_public_base_url' and 'Configuration.token' must be set.")
    return compute_short_hash(f'{configuration.api_public_base_url}{configuration.token}'.encode())


def to_crawlee_request(client_request: ClientRequest | HeadRequest | LockedHeadRequest) -> Request:
    """Convert an Apify API client's `Request` model to a Crawlee's `Request` model.

    Args:
        client_request: Request instances from Apify API client.

    Returns:
        `Request` instance from Crawlee with properly converted types.
    """
    # Dump to dict with mode='json' to serialize special types like AnyUrl
    request_dict = client_request.model_dump(by_alias=True, mode='json')

    # Validate and construct Crawlee Request from the serialized dict
    return Request.model_validate(request_dict)


def settle_pending_addition(
    requests_being_added: dict[str, asyncio.Future[bool]],
    request_id: str,
    *,
    committed: bool,
) -> None:
    """Resolve the in-flight add marker for a request, unblocking any concurrent call awaiting it.

    Args:
        requests_being_added: The client's map of in-flight `add_batch_of_requests` markers.
        request_id: ID of the request whose in-flight add has settled.
        committed: Whether the request was committed to the platform.
    """
    future = requests_being_added.pop(request_id, None)
    if future is not None and not future.done():
        future.set_result(committed)


async def resolve_awaited_in_flight(
    awaited_in_flight: Iterable[tuple[Request, asyncio.Future[bool]]],
    api_response: AddRequestsResponse,
) -> None:
    """Await concurrent in-flight adds of these requests and fold the outcome into `api_response`.

    Requests the concurrent add committed are reported as already present; the rest are reported unprocessed
    so the caller retries them rather than receiving false success.
    """
    for request, future in awaited_in_flight:
        # Shield the shared in-flight marker: cancelling this awaiting caller must not cancel the future, which
        # is owned by the original producer and may have other callers waiting on it.
        if await asyncio.shield(future):
            api_response.processed_requests.append(
                ProcessedRequest(
                    id=unique_key_to_request_id(request.unique_key),
                    unique_key=request.unique_key,
                    was_already_present=True,
                    was_already_handled=request.was_already_handled,
                )
            )
        else:
            api_response.unprocessed_requests.append(
                UnprocessedRequest(unique_key=request.unique_key, url=request.url, method=request.method)
            )
