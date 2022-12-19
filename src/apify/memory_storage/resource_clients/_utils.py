import base64
import hashlib
import io
import json
import mimetypes
import re
from typing import Any, NoReturn, Optional

from ...consts import REQUEST_ID_LENGTH, StorageTypes

uuid_regex = re.compile('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)


def _raise_on_non_existing(client_type: StorageTypes, id: str) -> NoReturn:
    raise ValueError(f'{client_type} with id: {id} does not exist.')


def _raise_on_duplicate_entry(client_type: StorageTypes, key_name: str, value: str) -> NoReturn:
    raise ValueError(f'{client_type} with {key_name}: {value} already exists.')


def _guess_file_extension(content_type: str) -> Optional[str]:
    # e.g. mimetypes.guess_extension('application/json ') does not work...
    actual_content_type = content_type.split(';')[0].strip()
    ext = mimetypes.guess_extension(actual_content_type)
    # Remove the leading dot if extension successfully parsed
    return ext[1:] if ext is not None else ext


def _is_content_type_json(content_type: str) -> bool:
    return bool(re.search(r'^application/json', content_type, flags=re.IGNORECASE))


def _is_content_type_xml(content_type: str) -> bool:
    return bool(re.search(r'^application/.*xml$', content_type, flags=re.IGNORECASE))


def _is_content_type_text(content_type: str) -> bool:
    return bool(re.search(r'^text/', content_type, flags=re.IGNORECASE))


def _is_file_or_bytes(value: Any) -> bool:
    # The check for IOBase is not ideal, it would be better to use duck typing,
    # but then the check would be super complex, judging from how the 'requests' library does it.
    # This way should be good enough for the vast majority of use cases, if it causes issues, we can improve it later.
    return isinstance(value, (bytes, bytearray, io.IOBase))


def _maybe_parse_body(body: bytes, content_type: str) -> Any:
    try:
        if _is_content_type_json(content_type):
            return json.loads(body)  # Returns any
        elif _is_content_type_xml(content_type) or _is_content_type_text(content_type):
            return body.decode('utf-8')  # TODO: Check if utf-8 can be assumed
    except ValueError as err:
        print('_maybe_parse_body error', err)
    return body


def _unique_key_to_request_id(unique_key: str) -> str:
    id = re.sub('(\+|\/|=)', '', base64.b64encode(hashlib.sha256(unique_key.encode('utf-8')).digest()).decode('utf-8'))

    return id[:REQUEST_ID_LENGTH] if len(id) > REQUEST_ID_LENGTH else id
