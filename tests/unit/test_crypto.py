from __future__ import annotations

import base64

import pytest

from .._utils import PRIVATE_KEY, PUBLIC_KEY
from apify._crypto import (
    _load_public_key,
    create_hmac_signature,
    crypto_random_object_id,
    encode_base62,
    load_private_key,
    private_decrypt,
    public_encrypt,
)


def test_encrypt_decrypt_various_strings() -> None:
    for value in [
        crypto_random_object_id(10),
        '👍',
        '!',
        '@',
        '#',
        '$',
        '%',
        '^',
        '&',
        '*',
        '(',
        ')',
        '-',
        '_',
        '=',
        '+',
        '[',
        ']',
        '{',
        '}',
        '|',
        ';',
        ':',
        '"',
        "'",
        ',',
        '.',
        '<',
        '>',
        '?',
        '/',
        '~',
    ]:
        encrypted = public_encrypt(value, public_key=PUBLIC_KEY)
        decrypted_value = private_decrypt(**encrypted, private_key=PRIVATE_KEY)
        assert decrypted_value == value


def test_decryption_fails_with_invalid_password() -> None:
    test_value = 'test'
    encrypted = public_encrypt(test_value, public_key=PUBLIC_KEY)
    encrypted['encrypted_password'] = base64.b64encode(b'invalid_password').decode('utf-8')

    with pytest.raises(ValueError, match=r'Ciphertext length must be equal to key size.'):
        private_decrypt(**encrypted, private_key=PRIVATE_KEY)


def test_decryption_fails_with_manipulated_cipher() -> None:
    test_value = 'test2'
    encrypted = public_encrypt(test_value, public_key=PUBLIC_KEY)
    encrypted['encrypted_value'] = base64.b64encode(
        b'invalid_cipher' + base64.b64decode(encrypted['encrypted_value'].encode('utf-8')),
    ).decode('utf-8')

    with pytest.raises(ValueError, match=r'Decryption failed, malformed encrypted value or password.'):
        private_decrypt(**encrypted, private_key=PRIVATE_KEY)


def test_same_value_produces_different_cipher_each_time() -> None:
    test_value = 'test3'
    encrypted1 = public_encrypt(test_value, public_key=PUBLIC_KEY)
    encrypted2 = public_encrypt(test_value, public_key=PUBLIC_KEY)
    assert encrypted1['encrypted_value'] != encrypted2['encrypted_value']


# Check if the method is compatible with js version of the same method in:
# https://github.com/apify/apify-shared-js/blob/master/packages/utilities/src/crypto.ts
def test_private_decrypt_with_node_js_encrypted_value() -> None:
    value = 'encrypted_with_node_js'
    # This was encrypted with nodejs version of the same method.
    encrypted_value_with_node_js = {
        'encrypted_password': 'lw0ez64/T1UcCQMLfhucZ6VIfMcf/TKni7PmXlL/ZRA4nmdGYz7/YQUzGWzKbLChrpqbG21DHxPIubUIQFDFE1ASkLvoSd0Ks8/wjKHMyhp+hsg5aSh9EZK6pBFpp6FeHoinV80+UURTvJuSVbWd1Orw5Frl41taP6RK3uNJlXikmgs8Xc7mShFEENgkz6y9+Pbe7jpcKkaJ2U/h7FN0eNON189kNFYVuAE1n2N6C3Q7dFnjl2e1btqErvg5Vu7ZS4BbX3wgC2qLYySGnqI3BNI5VGhAnncnQcjHb+85qG+LKoPekgY9I0s0kGMxiz/bmy1mYm9O+Lj1mbVUr7BDjQ==',  # noqa: E501
        'encrypted_value': 'k8nkZDCi0hRfBc0RRefxeSHeGV0X60N03VCrhRhENKXBjrF/tEg=',
    }
    decrypted_value = private_decrypt(
        **encrypted_value_with_node_js,
        private_key=PRIVATE_KEY,
    )

    assert decrypted_value == value


def test_crypto_random_object_id_length_and_charset() -> None:
    assert len(crypto_random_object_id()) == 17
    assert len(crypto_random_object_id(5)) == 5
    long_random_object_id = crypto_random_object_id(1000)
    for char in long_random_object_id:
        assert char in 'abcdefghijklmnopqrstuvwxyzABCEDFGHIJKLMNOPQRSTUVWXYZ0123456789'


@pytest.mark.parametrize(('test_input', 'expected'), [(0, '0'), (10, 'a'), (999999999, '15FTGf')])
def test_encode_base62(test_input: int, expected: str) -> None:
    assert encode_base62(test_input) == expected


# This test ensures compatibility with the JavaScript version of the same method.
# https://github.com/apify/apify-shared-js/blob/master/packages/utilities/src/hmac.ts
def test_create_valid_hmac_signature() -> None:
    # This test uses the same secret key and message as in JS tests.
    secret_key = 'hmac-secret-key'
    message = 'hmac-message-to-be-authenticated'
    assert create_hmac_signature(secret_key, message) == 'pcVagAsudj8dFqdlg7mG'


def test_create_same_hmac() -> None:
    # This test uses the same secret key and message as in JS tests.
    secret_key = 'hmac-same-secret-key'
    message = 'hmac-same-message-to-be-authenticated'
    assert create_hmac_signature(secret_key, message) == 'FYMcmTIm3idXqleF1Sw5'


def test_encrypt_decrypt_empty_string() -> None:
    """Test that encrypting and decrypting an empty string works correctly."""
    encrypted = public_encrypt('', public_key=PUBLIC_KEY)
    decrypted = private_decrypt(**encrypted, private_key=PRIVATE_KEY)
    assert decrypted == ''


def test_encrypt_decrypt_very_long_string() -> None:
    """Test that encrypting and decrypting a very long string works correctly."""
    long_string = 'A' * 10000
    encrypted = public_encrypt(long_string, public_key=PUBLIC_KEY)
    decrypted = private_decrypt(**encrypted, private_key=PRIVATE_KEY)
    assert decrypted == long_string


def test_hmac_with_empty_message() -> None:
    """Test HMAC signature generation with an empty message."""
    signature = create_hmac_signature('some-key', '')
    assert isinstance(signature, str)
    assert len(signature) > 0
    # Same key and empty message should always produce the same signature
    assert create_hmac_signature('some-key', '') == signature


def test_encode_base62_large_number() -> None:
    """Test encode_base62 with a large number."""
    result = encode_base62(2**64)
    assert isinstance(result, str)
    assert len(result) > 0
    # Verify all characters are in the base62 charset
    charset = '0123456789abcdefghijklmnopqrstuvwxyzABCEDFGHIJKLMNOPQRSTUVWXYZ'
    for char in result:
        assert char in charset


def test_load_private_key_invalid_type() -> None:
    """Test that load_private_key raises TypeError for non-RSA keys."""
    from unittest.mock import patch

    with (
        patch('apify._crypto.serialization.load_pem_private_key', return_value='not_an_rsa_key'),
        pytest.raises(TypeError, match='Invalid private key'),
    ):
        load_private_key('ZHVtbXk=', 'password')


def test_load_public_key_invalid_type() -> None:
    """Test that _load_public_key raises TypeError for non-RSA keys."""
    from unittest.mock import patch

    with (
        patch('apify._crypto.serialization.load_pem_public_key', return_value='not_an_rsa_key'),
        pytest.raises(TypeError, match='Invalid public key'),
    ):
        _load_public_key('ZHVtbXk=')


@pytest.mark.parametrize(
    'value',
    [
        pytest.param('just a string', id='string'),
        pytest.param(42, id='int'),
        pytest.param([1, 2, 3], id='list'),
        pytest.param(None, id='none'),
    ],
)
def test_decrypt_input_secrets_non_dict(value: object) -> None:
    """Test that decrypt_input_secrets returns non-dict input unchanged."""
    from apify._crypto import decrypt_input_secrets

    result = decrypt_input_secrets(PRIVATE_KEY, value)
    if value is None:
        assert result is None
    else:
        assert result == value
