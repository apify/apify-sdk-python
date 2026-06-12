from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict, Field

from apify.scrapy._serialization import _MAX_ERROR_VALUE_REPR_LEN, decode_from_json, encode_to_json


def _round_trip(data: dict) -> dict:
    """Encode then decode a dict through the serializer."""
    decoded = decode_from_json(encode_to_json(data))
    assert isinstance(decoded, dict)
    return decoded


class _LongRepr:
    """A helper whose repr is long enough to trigger truncation in a serialization error message."""

    def __repr__(self) -> str:
        return 'x' * 500


def test_bytes_body_round_trips() -> None:
    """A binary `body` round-trips unchanged (base64-encoded inside the JSON)."""
    assert _round_trip({'body': b'\x00\x01\xff binary'})['body'] == b'\x00\x01\xff binary'


def test_str_body_round_trips_to_bytes() -> None:
    """A `str` body is encoded as its UTF-8 bytes and comes back as `bytes` (Scrapy stores bytes)."""
    assert _round_trip({'body': 'hello'})['body'] == b'hello'


def test_empty_str_body_round_trips() -> None:
    """An empty `str` body round-trips to empty `bytes`."""
    assert _round_trip({'body': ''})['body'] == b''


def test_bytes_headers_round_trip() -> None:
    """Scrapy-style `{bytes: [bytes]}` headers, including binary values, round-trip unchanged."""
    data = {'headers': {b'Content-Type': [b'text/html'], b'X-Bin': [b'\x00\xff']}}
    assert _round_trip(data)['headers'] == {b'Content-Type': [b'text/html'], b'X-Bin': [b'\x00\xff']}


def test_str_header_value_round_trips_to_bytes() -> None:
    """A `str` header value is encoded as its UTF-8 bytes and comes back as `bytes` (Scrapy uses bytes)."""
    assert _round_trip({'headers': {b'Content-Type': ['text/html']}})['headers'] == {b'Content-Type': [b'text/html']}


def test_bare_header_value_is_normalized_to_list() -> None:
    """A header value not wrapped in a list is normalized to a single-element list on round-trip."""
    assert _round_trip({'headers': {b'X-Single': b'one'}})['headers'] == {b'X-Single': [b'one']}


def test_non_ascii_is_not_escaped() -> None:
    """Non-ASCII text stays in its UTF-8 form instead of ASCII escape sequences, which would bloat storage."""
    encoded = encode_to_json({'meta': {'name': 'Ñoño café 日本語'}})
    assert 'Ñoño café 日本語' in encoded
    assert '\\u' not in encoded
    assert decode_from_json(encoded)['meta']['name'] == 'Ñoño café 日本語'


def test_pydantic_model_is_dumped_by_alias() -> None:
    """A pydantic model in `meta` is dumped to a plain dict using its serialization aliases."""

    class Model(BaseModel):
        first: int = Field(serialization_alias='First')

    encoded = encode_to_json({'meta': {'m': Model(first=1)}})
    assert decode_from_json(encoded)['meta']['m'] == {'First': 1}


def test_pydantic_model_with_datetime_field_round_trips() -> None:
    """A pydantic model with a `datetime` field is dumped in JSON mode, so the request is stored, not dropped."""

    class Model(BaseModel):
        when: datetime

    encoded = encode_to_json({'meta': {'m': Model(when=datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC))}})
    assert decode_from_json(encoded)['meta']['m'] == {'when': '2020-01-02T03:04:05Z'}


def test_pydantic_model_with_non_serializable_field_raises() -> None:
    """A model field that even JSON mode cannot dump raises the clear `TypeError`, not a bare pydantic error."""

    class Model(BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        obj: object

    with pytest.raises(TypeError, match='JSON-serializable'):
        encode_to_json({'meta': {'m': Model(obj=object())}})


def test_tuple_is_coerced_to_list() -> None:
    """Documented limitation: JSON has no tuple type, so a tuple round-trips as a list."""
    assert _round_trip({'meta': {'coords': (1, 2, 3)}})['meta']['coords'] == [1, 2, 3]


def test_non_string_dict_keys_are_coerced_to_strings() -> None:
    """Documented limitation: JSON object keys are strings, so `{1: 'a'}` round-trips as `{'1': 'a'}`."""
    assert _round_trip({'cb_kwargs': {'m': {1: 'a'}}})['cb_kwargs']['m'] == {'1': 'a'}


def test_non_serializable_value_raises_with_type_and_repr() -> None:
    """A value JSON cannot represent raises a `TypeError` naming the offending type and value."""
    when = datetime(2020, 1, 2, 3, 4, 5, tzinfo=UTC)
    with pytest.raises(TypeError) as exc_info:
        encode_to_json({'meta': {'when': when}})

    # The user-facing message points at meta/cb_kwargs; the chained cause names the offending value.
    assert 'JSON-serializable' in str(exc_info.value)
    assert 'datetime' in str(exc_info.value.__cause__)


def test_long_value_repr_is_truncated_in_error() -> None:
    """A non-serializable value with a very long repr is truncated (with an ellipsis) so it cannot bloat the log."""
    with pytest.raises(TypeError) as exc_info:
        encode_to_json({'meta': {'big': _LongRepr()}})

    cause = str(exc_info.value.__cause__)
    assert cause.endswith('...')
    assert cause.count('x') == _MAX_ERROR_VALUE_REPR_LEN


def test_encode_rejects_non_dict() -> None:
    """Encoding a non-dict top-level value raises `TypeError`."""
    with pytest.raises(TypeError, match='Expected a dict'):
        encode_to_json(['not', 'a', 'dict'])  # ty: ignore[invalid-argument-type]


def test_decode_of_non_dict_json_returns_value_as_is() -> None:
    """JSON that decodes to a non-dict (a list, a bare string) is returned unchanged, not coerced or rejected."""
    assert decode_from_json('[1, 2, 3]') == [1, 2, 3]
    assert decode_from_json('"hello"') == 'hello'


def test_decode_rejects_non_base64_body() -> None:
    """A non-base64 `body` is rejected loudly (the `validate=True` guard), not silently decoded to garbage."""
    with pytest.raises(ValueError, match='base64'):
        decode_from_json('{"body": "not valid base64 !!!"}')


def test_decode_rejects_non_base64_header_value() -> None:
    """A non-base64 header value is rejected loudly rather than silently decoded to garbage."""
    with pytest.raises(ValueError, match='base64'):
        decode_from_json('{"headers": {"X-Test": ["not valid base64 !!!"]}}')
