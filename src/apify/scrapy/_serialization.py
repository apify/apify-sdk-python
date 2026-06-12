"""JSON serialization of Scrapy requests and cached responses for storage on the Apify platform.

Scrapy requests and cached responses are stored in the Apify request queue and key-value store, which hold JSON.
They are therefore serialized as JSON here.

Only `body` (`bytes`) and `headers` (`{bytes: [bytes]}`) are not natively JSON-serializable. Both live at fixed keys
and are base64-encoded in place. A `str` `body` is encoded as UTF-8 bytes and deserialized as `bytes`, matching
Scrapy, which always stores `body` as `bytes`.

Pydantic models, such as Crawlee's `UserData`, are dumped with `model_dump(mode='json')`, which converts
non-JSON-native fields into JSON-compatible values. For example, `datetime` fields are stored as ISO-8601 strings.

All other values, notably `meta` and `cb_kwargs`, must already be JSON-serializable. Non-JSON-serializable values,
such as `datetime`, `set`, `Decimal`, or arbitrary objects, fail serialization with a clear error naming the
offending value. The request is skipped rather than stored in a corrupted form.

No in-band sentinel is used, so user values cannot collide with the encoding.

Known JSON limitations: values in `meta` and `cb_kwargs` are subject to JSON coercions. A `tuple` round-trips as
a `list`, and non-string `dict` keys round-trip as strings; for example, `{1: 'a'}` becomes `{'1': 'a'}`.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from pydantic import BaseModel

# Cap the offending value's repr in a serialization error message so a huge value cannot bloat the log.
_MAX_ERROR_VALUE_REPR_LEN = 200


def encode_to_json(data: dict[str, Any]) -> str:
    """Serialize a Scrapy request/response dict to a JSON string.

    The `body` and `headers` fields are base64-encoded in place (a `str` `body` via its UTF-8 bytes); pydantic
    models are dumped to plain dicts. A `TypeError` is raised if any other value cannot be JSON-encoded.

    Args:
        data: The dict to serialize, e.g. the output of `scrapy.Request.to_dict()`.

    Returns:
        The JSON-encoded string.
    """
    if not isinstance(data, dict):
        raise TypeError(f'Expected a dict to serialize, got {type(data)}')

    safe = dict(data)

    # `body` is base64-encoded so binary payloads survive; a `str` body is taken as its UTF-8 bytes, which keeps
    # encode/decode symmetric (decode always base64-decodes `body` back to `bytes`).
    body = safe.get('body')
    if isinstance(body, (bytes, str)):
        raw_body = body.encode('utf-8') if isinstance(body, str) else body
        safe['body'] = base64.b64encode(raw_body).decode('ascii')

    if isinstance(safe.get('headers'), dict):
        safe['headers'] = _encode_headers(safe['headers'])

    try:
        # `ensure_ascii=False` keeps non-ASCII URLs/meta as their UTF-8 form instead of `\uXXXX` escapes, which
        # would otherwise roughly double the size of non-Latin text in storage.
        return json.dumps(safe, default=_json_default, ensure_ascii=False)
    # `ValueError` covers pydantic's `PydanticSerializationError`, raised when a model field cannot be dumped
    # to JSON even in JSON mode.
    except (TypeError, ValueError) as exc:
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

    # `validate=True` makes a non-base64 body raise loudly instead of silently decoding to garbage.
    if isinstance(data.get('body'), str):
        data['body'] = base64.b64decode(data['body'], validate=True)

    if isinstance(data.get('headers'), dict):
        data['headers'] = _decode_headers(data['headers'])

    return data


def _json_default(obj: Any) -> Any:
    """Fallback for values `json.dumps` cannot serialize: pydantic models are dumped, anything else raises.

    The error names the offending value (type and a truncated repr) so a failed serialization points straight
    at the bad `meta`/`cb_kwargs` entry instead of just reporting that something failed.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode='json', by_alias=True)
    value_repr = repr(obj)
    if len(value_repr) > _MAX_ERROR_VALUE_REPR_LEN:
        value_repr = value_repr[:_MAX_ERROR_VALUE_REPR_LEN] + '...'
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON-serializable: {value_repr}')


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
        decoded[bytes_key] = [base64.b64decode(item, validate=True) for item in values]
    return decoded


def _b64encode_value(value: Any) -> str:
    """Base64-encode a single header value.

    Scrapy stores header values as `bytes`; a `str` is encoded as its UTF-8 bytes. Any other type is coerced with
    `str()` as a lenient last resort. That coercion is lossy (e.g. `5` becomes `b'5'`), but Scrapy does not produce
    non-`bytes`/`str` header values, so it is not hit on the real path.
    """
    raw = value if isinstance(value, bytes) else str(value).encode('utf-8')
    return base64.b64encode(raw).decode('ascii')
