from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel

# Scrapy requests and cached responses are stored in the Apify request queue and key-value store,
# which hold JSON, so they are serialized as JSON here rather than pickled.
#
# Only `body` (`bytes`) and `headers` (`{bytes: [bytes]}`) are not natively JSON-serializable; both
# sit at fixed keys and are base64-encoded in place. Pydantic models such as Crawlee's `UserData`
# are dumped via `model_dump()`. Everything else, notably `meta` and `cb_kwargs`, must already be
# JSON-serializable, otherwise serialization fails with a clear error. No in-band sentinel is used,
# so no user value can collide with the encoding.


def encode_to_json(data: dict[str, Any]) -> str:
    """Serialize a Scrapy request/response dict to a JSON string.

    The binary `body` and `headers` fields are base64-encoded in place; pydantic models are dumped
    to plain dicts. A `TypeError` is raised if any other value cannot be JSON-encoded.

    Args:
        data: The dict to serialize, e.g. the output of `scrapy.Request.to_dict()`.

    Returns:
        The JSON-encoded string.
    """
    if not isinstance(data, dict):
        raise TypeError(f'Expected a dict to serialize, got {type(data)}')

    safe = dict(data)

    if isinstance(safe.get('body'), bytes):
        safe['body'] = base64.b64encode(safe['body']).decode('ascii')

    if isinstance(safe.get('headers'), dict):
        safe['headers'] = _encode_headers(safe['headers'])

    try:
        return json.dumps(safe, default=_json_default)
    except TypeError as exc:
        raise TypeError(
            'Failed to JSON-serialize a Scrapy request/response for storage on the Apify platform. '
            'All values in `meta` and `cb_kwargs` must be JSON-serializable (str, int, float, bool, None, '
            'list, dict, or a pydantic model).'
        ) from exc


def decode_from_json(text: str) -> Any:
    """Reconstruct a Scrapy request/response dict from a string produced by `encode_to_json`.

    The base64-encoded `body` and `headers` fields are decoded back to their `bytes` representation.

    Args:
        text: The JSON-encoded string.

    Returns:
        The decoded object (a dict for valid request/response payloads).
    """
    data = json.loads(text)
    if not isinstance(data, dict):
        return data

    if isinstance(data.get('body'), str):
        data['body'] = base64.b64decode(data['body'])

    if isinstance(data.get('headers'), dict):
        data['headers'] = _decode_headers(data['headers'])

    return data


def _json_default(obj: Any) -> Any:
    """Fallback for values `json.dumps` cannot serialize: pydantic models are dumped, anything else raises."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(by_alias=True)
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON-serializable')


def _encode_headers(headers: dict[Any, Any]) -> dict[str, list[str]]:
    """Encode a Scrapy `{bytes: [bytes]}` headers mapping to a JSON-safe `{str: [base64-str]}`."""
    encoded: dict[str, list[str]] = {}
    for key, value in headers.items():
        str_key = key.decode('latin-1') if isinstance(key, bytes) else key
        values = value if isinstance(value, (list, tuple)) else [value]
        encoded[str_key] = [_b64encode_value(item) for item in values]
    return encoded


def _decode_headers(headers: dict[str, Any]) -> dict[bytes, list[bytes]]:
    """Reverse `_encode_headers`, restoring the `{bytes: [bytes]}` mapping Scrapy expects."""
    decoded: dict[bytes, list[bytes]] = {}
    for key, value in headers.items():
        bytes_key = key.encode('latin-1') if isinstance(key, str) else key
        values = value if isinstance(value, list) else [value]
        decoded[bytes_key] = [base64.b64decode(item) for item in values]
    return decoded


def _b64encode_value(value: Any) -> str:
    """Base64-encode a single header value, coercing non-bytes values to bytes first."""
    raw = value if isinstance(value, bytes) else str(value).encode('utf-8')
    return base64.b64encode(raw).decode('ascii')
