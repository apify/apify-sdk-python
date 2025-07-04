from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from apify_shared.consts import ApifyEnvVars
from apify_shared.utils import json_dumps

from ..test_crypto import PRIVATE_KEY_PASSWORD, PRIVATE_KEY_PEM_BASE64, PUBLIC_KEY
from apify import Actor
from apify._consts import ENCRYPTED_STRING_VALUE_PREFIX, ENCRYPTED_JSON_VALUE_PREFIX
from apify._crypto import public_encrypt

if TYPE_CHECKING:
    from crawlee.storage_clients import MemoryStorageClient


# NOTE: We only test the key-value store methods available on Actor class/instance.
# Actual tests for the implementations are in storages/.
async def test_open_returns_same_references() -> None:
    async with Actor:
        kvs1 = await Actor.open_key_value_store()
        kvs2 = await Actor.open_key_value_store()
        assert kvs1 is kvs2

        kvs_name = 'non-default'
        kvs_by_name_1 = await Actor.open_key_value_store(name=kvs_name)
        kvs_by_name_2 = await Actor.open_key_value_store(name=kvs_name)
        assert kvs_by_name_1 is kvs_by_name_2

        kvs_by_id_1 = await Actor.open_key_value_store(id=kvs_by_name_1._id)
        kvs_by_id_2 = await Actor.open_key_value_store(id=kvs_by_name_1._id)
        assert kvs_by_id_1 is kvs_by_name_1
        assert kvs_by_id_2 is kvs_by_id_1


async def test_open_throws_without_init() -> None:
    with pytest.raises(RuntimeError):
        await Actor.open_key_value_store()


async def test_set_and_get_value() -> None:
    test_key = 'test_key'
    test_value = 'test_value'
    test_content_type = 'text/plain'
    async with Actor as my_actor:
        await my_actor.set_value(key=test_key, value=test_value, content_type=test_content_type)
        value = await my_actor.get_value(key=test_key)
        assert value == test_value


async def test_get_input(memory_storage_client: MemoryStorageClient) -> None:
    input_key = 'INPUT'
    test_input = {'foo': 'bar'}

    await memory_storage_client.key_value_stores().get_or_create(id='default')
    await memory_storage_client.key_value_store('default').set_record(
        key=input_key,
        value=json_dumps(test_input),
        content_type='application/json',
    )

    async with Actor as my_actor:
        input = await my_actor.get_input()  # noqa: A001
        assert input['foo'] == test_input['foo']


async def test_get_input_with_encrypted_secrets(
    monkeypatch: pytest.MonkeyPatch,
    memory_storage_client: MemoryStorageClient,
) -> None:
    monkeypatch.setenv(ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_FILE, PRIVATE_KEY_PEM_BASE64)
    monkeypatch.setenv(ApifyEnvVars.INPUT_SECRETS_PRIVATE_KEY_PASSPHRASE, PRIVATE_KEY_PASSWORD)

    input_key = 'INPUT'
    secret_string_legacy = 'secret-string'
    secret_string = 'secret-string'
    secret_object = {'foo': 'bar', 'baz': 'qux'}
    secret_array = ['foo', 'bar', 'baz']

    # The legacy encryption format uses ENCRYPTED_STRING_VALUE_PREFIX prefix, value in raw string and does not include schemahash.
    # The new format uses ENCRYPTED_JSON_VALUE_PREFIX prefix, value in JSON format and includes schemahash.
    # We are testing both formats to ensure backward compatibility.

    encrypted_string_legacy = public_encrypt(secret_string_legacy, public_key=PUBLIC_KEY)
    encrypted_string = public_encrypt(json_dumps(secret_string), public_key=PUBLIC_KEY)
    encrypted_object = public_encrypt(json_dumps(secret_object), public_key=PUBLIC_KEY)
    encrypted_array = public_encrypt(json_dumps(secret_array), public_key=PUBLIC_KEY)

    input_with_secret = {
        'foo': 'bar',
        'secret_string_legacy': f'{ENCRYPTED_STRING_VALUE_PREFIX}:{encrypted_string_legacy["encrypted_password"]}:{encrypted_string_legacy["encrypted_value"]}',
        'secret_string': f'{ENCRYPTED_JSON_VALUE_PREFIX}:schemahash:{encrypted_string["encrypted_password"]}:{encrypted_string["encrypted_value"]}',
        'secret_object': f'{ENCRYPTED_JSON_VALUE_PREFIX}:schemahash:{encrypted_object["encrypted_password"]}:{encrypted_object["encrypted_value"]}',
        'secret_array': f'{ENCRYPTED_JSON_VALUE_PREFIX}:schemahash:{encrypted_array["encrypted_password"]}:{encrypted_array["encrypted_value"]}',
    }

    await memory_storage_client.key_value_stores().get_or_create(id='default')
    await memory_storage_client.key_value_store('default').set_record(
        key=input_key,
        value=json_dumps(input_with_secret),
        content_type='application/json',
    )

    async with Actor as my_actor:
        input = await my_actor.get_input()  # noqa: A001
        assert input['foo'] == input_with_secret['foo']
        assert input['secret_string_legacy'] == secret_string_legacy
        assert input['secret_string'] == secret_string
        assert input['secret_object'] == secret_object
        assert input['secret_array'] == secret_array
