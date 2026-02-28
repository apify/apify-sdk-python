from __future__ import annotations

from base64 import b64decode, b64encode
from enum import Enum
from typing import Any

from pydantic import BaseModel


def prepare_for_json(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable values to JSON-safe representations.

    Bytes values are converted to dicts with a `__bytes_b64__` key. Bytes dict keys
    are decoded to UTF-8 strings. Pydantic models are converted via `model_dump(mode='json')`.
    Enum values are converted to their underlying value.
    """
    if isinstance(obj, bytes):
        return {'__bytes_b64__': b64encode(obj).decode('ascii')}
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode='json')
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {(k.decode('utf-8') if isinstance(k, bytes) else k): prepare_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [prepare_for_json(item) for item in obj]
    return obj


def restore_from_json(obj: Any) -> Any:
    """Recursively restore bytes values from their base64-encoded JSON representations."""
    if isinstance(obj, dict):
        if '__bytes_b64__' in obj and len(obj) == 1:
            return b64decode(obj['__bytes_b64__'])
        return {k: restore_from_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [restore_from_json(item) for item in obj]
    return obj
