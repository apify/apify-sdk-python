from __future__ import annotations

import re
from datetime import timedelta

EVENT_LISTENERS_TIMEOUT = timedelta(seconds=5)

BASE64_REGEXP = '[-A-Za-z0-9+/]*={0,3}'
ENCRYPTED_STRING_VALUE_PREFIX = 'ENCRYPTED_VALUE'
ENCRYPTED_JSON_VALUE_PREFIX = 'ENCRYPTED_JSON'
ENCRYPTED_INPUT_VALUE_REGEXP = re.compile(f'^({ENCRYPTED_STRING_VALUE_PREFIX}|{ENCRYPTED_JSON_VALUE_PREFIX}):(?:({BASE64_REGEXP}):)?({BASE64_REGEXP}):({BASE64_REGEXP})$')
