from __future__ import annotations

import re
from base64 import b64encode
from hashlib import sha256
from typing import TYPE_CHECKING

from crawlee._utils.crypto import compute_short_hash

from apify import Request

if TYPE_CHECKING:
    from apify_client._models import HeadRequest, LockedHeadRequest
    from apify_client._models import Request as ClientRequest

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
