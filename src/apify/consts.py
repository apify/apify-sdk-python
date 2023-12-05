from __future__ import annotations

import re
import warnings
from enum import Enum
from typing import Any

from apify_shared.consts import BOOL_ENV_VARS as _BOOL_ENV_VARS  # noqa: F401
from apify_shared.consts import DATETIME_ENV_VARS as _DATETIME_ENV_VARS  # noqa: F401
from apify_shared.consts import FLOAT_ENV_VARS as _FLOAT_ENV_VARS  # noqa: F401
from apify_shared.consts import INTEGER_ENV_VARS as _INTEGER_ENV_VARS  # noqa: F401
from apify_shared.consts import STRING_ENV_VARS as _STRING_ENV_VARS  # noqa: F401
from apify_shared.consts import ActorEventTypes as _ActorEventTypes  # noqa: F401
from apify_shared.consts import ActorExitCodes as _ActorExitCodes  # noqa: F401
from apify_shared.consts import ApifyEnvVars as _ApifyEnvVars  # noqa: F401

DEPRECATED_NAMES = [
    'BOOL_ENV_VARS',
    'DATETIME_ENV_VARS',
    'FLOAT_ENV_VARS',
    'INTEGER_ENV_VARS',
    'STRING_ENV_VARS',
    'ActorEventTypes',
    'ActorExitCodes',
    'ApifyEnvVars',
]


# The following piece of code is highly inspired by the example in https://peps.python.org/pep-0562.
# The else branch is missing intentionally! Check the following discussion for details:
# https://github.com/apify/apify-client-python/pull/132#discussion_r1277294315.
def __getattr__(name: str) -> Any:
    if name in DEPRECATED_NAMES:
        warnings.warn(
            (
                f'Importing "{name}" from "apify_client.consts" is deprecated and will be removed in the future. '
                'Please use "apify_shared" library instead.'
            ),
            category=DeprecationWarning,
            stacklevel=2,
        )
        return globals()[f'_{name}']
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


class StorageTypes(str, Enum):
    """Possible Apify storage types."""

    DATASET = 'Dataset'
    KEY_VALUE_STORE = 'Key-value store'
    REQUEST_QUEUE = 'Request queue'


DEFAULT_API_PARAM_LIMIT = 1000

REQUEST_ID_LENGTH = 15

REQUEST_QUEUE_HEAD_MAX_LIMIT = 1000

EVENT_LISTENERS_TIMEOUT_SECS = 5

BASE64_REGEXP = '[-A-Za-z0-9+/]*={0,3}'
ENCRYPTED_INPUT_VALUE_PREFIX = 'ENCRYPTED_VALUE'
ENCRYPTED_INPUT_VALUE_REGEXP = re.compile(f'^{ENCRYPTED_INPUT_VALUE_PREFIX}:({BASE64_REGEXP}):({BASE64_REGEXP})$')

# 9MB
MAX_PAYLOAD_SIZE_BYTES = 9437184
