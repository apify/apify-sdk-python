from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, Field

from apify.scrapy._serialization import decode_from_json, encode_to_json


def _round_trip(data: dict) -> dict:
    """Encode then decode a dict through the serializer."""
    decoded = decode_from_json(encode_to_json(data))
    assert isinstance(decoded, dict)
    return decoded


# --- body encoding (bytes/str symmetry) ---


def test_bytes_body_round_trips() -> None:
    assert _round_trip({'body': b'\x00\x01\xff binary'})['body'] == b'\x00\x01\xff binary'


def test_str_body_round_trips_to_bytes() -> None:
    """A `str` body is encoded as its UTF-8 bytes and comes back as `bytes` (Scrapy stores bytes).

    Without symmetric handling a `str` body is left unencoded yet unconditionally base64-decoded on the
    way back, which corrupts it or raises.
    """
    assert _round_trip({'body': 'hello'})['body'] == b'hello'


def test_empty_str_body_round_trips() -> None:
    assert _round_trip({'body': ''})['body'] == b''


# --- headers ---


def test_bytes_headers_round_trip() -> None:
    data = {'headers': {b'Content-Type': [b'text/html'], b'X-Bin': [b'\x00\xff']}}
    assert _round_trip(data)['headers'] == {b'Content-Type': [b'text/html'], b'X-Bin': [b'\x00\xff']}


# --- non-ASCII text is kept as UTF-8 (ensure_ascii=False) ---


def test_non_ascii_is_not_escaped() -> None:
    """Non-ASCII text stays in its UTF-8 form instead of ASCII escape sequences, which would bloat storage."""
    encoded = encode_to_json({'meta': {'name': 'Ñoño café 日本語'}})
    assert 'Ñoño café 日本語' in encoded
    assert '\\u' not in encoded
    assert decode_from_json(encoded)['meta']['name'] == 'Ñoño café 日本語'


# --- pydantic models are dumped ---


def test_pydantic_model_is_dumped_by_alias() -> None:
    class Model(BaseModel):
        first: int = Field(serialization_alias='First')

    encoded = encode_to_json({'meta': {'m': Model(first=1)}})
    assert decode_from_json(encoded)['meta']['m'] == {'First': 1}


# --- documented JSON coercions (a breaking change vs. pickle) ---


def test_tuple_is_coerced_to_list() -> None:
    """Documented limitation: JSON has no tuple type, so a tuple round-trips as a list."""
    assert _round_trip({'meta': {'coords': (1, 2, 3)}})['meta']['coords'] == [1, 2, 3]


def test_non_string_dict_keys_are_coerced_to_strings() -> None:
    """Documented limitation: JSON object keys are strings, so `{1: 'a'}` round-trips as `{'1': 'a'}`."""
    assert _round_trip({'cb_kwargs': {'m': {1: 'a'}}})['cb_kwargs']['m'] == {'1': 'a'}


# --- values JSON cannot represent fail loudly with a useful message ---


def test_non_serializable_value_raises_with_type_and_repr() -> None:
    """A value JSON cannot represent raises a `TypeError` naming the offending type and value."""
    when = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    with pytest.raises(TypeError) as exc_info:
        encode_to_json({'meta': {'when': when}})

    # The user-facing message points at meta/cb_kwargs; the chained cause names the offending value.
    assert 'JSON-serializable' in str(exc_info.value)
    assert 'datetime' in str(exc_info.value.__cause__)


def test_encode_rejects_non_dict() -> None:
    with pytest.raises(TypeError, match='Expected a dict'):
        encode_to_json(['not', 'a', 'dict'])  # ty: ignore[invalid-argument-type]
