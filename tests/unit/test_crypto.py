from __future__ import annotations

import base64

import pytest

from apify._crypto import (
    _load_public_key,
    create_hmac_signature,
    crypto_random_object_id,
    encode_base62,
    load_private_key,
    private_decrypt,
    public_encrypt,
)

# NOTE: Uses the same keys as in:
# https://github.com/apify/apify-shared-js/blob/master/test/crypto.test.ts
PRIVATE_KEY_PEM_BASE64 = 'LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpQcm9jLVR5cGU6IDQsRU5DUllQVEVECkRFSy1JbmZvOiBERVMtRURFMy1DQkMsNTM1QURERjIzNUQ4QkFGOQoKMXFWUzl0S0FhdkVhVUVFMktESnpjM3plMk1lZkc1dmVEd2o1UVJ0ZkRaMXdWNS9VZmIvcU5sVThTSjlNaGhKaQp6RFdrWExueUUzSW0vcEtITVZkS0czYWZkcFRtcis2TmtidXptd0dVMk0vSWpzRjRJZlpad0lGbGJoY09jUnp4CmZmWVIvTlVyaHNrS1RpNGhGV0lBUDlLb3Z6VDhPSzNZY3h6eVZQWUxYNGVWbWt3UmZzeWkwUU5Xb0tGT3d0ZC8KNm9HYzFnd2piRjI5ZDNnUThZQjFGWmRLa1AyMTJGbkt1cTIrUWgvbE1zTUZrTHlTQTRLTGJ3ZG1RSXExbE1QUwpjbUNtZnppV3J1MlBtNEZoM0dmWlQyaE1JWHlIRFdEVzlDTkxKaERodExOZ2RRamFBUFpVT1E4V2hwSkE5MS9vCjJLZzZ3MDd5Z2RCcVd5dTZrc0pXcjNpZ1JpUEJ5QmVNWEpEZU5HY3NhaUZ3Q2c5eFlja1VORXR3NS90WlRsTjIKSEdZV0NpVU5Ed0F2WllMUHR1SHpIOFRFMGxsZm5HR0VuVC9QQlp1UHV4andlZlRleE1mdzFpbGJRU3lkcy9HMgpOOUlKKzkydms0N0ZXR2NOdGh1Q3lCbklva0NpZ0c1ZlBlV2IwQTdpdjk0UGtwRTRJZ3plc0hGQ0ZFQWoxWldLCnpQdFRBQlkwZlJrUzBNc3UwMHYxOXloTTUrdFUwYkVCZWo2eWpzWHRoYzlwS01hcUNIZWlQTC9TSHRkaWsxNVMKQmU4Sml4dVJxZitUeGlYWWVuNTg2aDlzTFpEYzA3cGpkUGp2NVNYRnBYQjhIMlVxQ0tZY2p4R3RvQWpTV0pjWApMNHc3RHNEby80bVg1N0htR09iamlCN1ZyOGhVWEJDdFh2V0dmQXlmcEFZNS9vOXowdm4zREcxaDc1NVVwdDluCkF2MFZrbm9qcmJVYjM1ZlJuU1lYTVltS01LSnpNRlMrdmFvRlpwV0ZjTG10cFRWSWNzc0JGUEYyZEo3V1c0WHMKK0d2Vkl2eFl3S2wyZzFPTE1TTXRZa09vekdlblBXTzdIdU0yMUVKVGIvbHNEZ25GaTkrYWRGZHBLY3R2cm0zdgpmbW1HeG5pRmhLU05GU0xtNms5YStHL2pjK3NVQVBhb2FZNEQ3NHVGajh0WGp0eThFUHdRRGxVUGRVZld3SE9PClF3bVgyMys1REh4V0VoQy91Tm8yNHNNY2ZkQzFGZUpBV281bUNuVU5vUVVmMStNRDVhMzNJdDhhMmlrNUkxUWoKeSs1WGpRaG0xd3RBMWhWTWE4aUxBR0toT09lcFRuK1VBZHpyS0hvNjVtYzNKbGgvSFJDUXJabnVxWkErK0F2WgpjeWU0dWZGWC8xdmRQSTdLb2Q0MEdDM2dlQnhweFFNYnp1OFNUcGpOcElJRkJvRVc5dFRhemUzeHZXWnV6dDc0CnFjZS8xWURuUHBLeW5lM0xGMk94VWoyYWVYUW5YQkpYcGhTZTBVTGJMcWJtUll4bjJKWkl1d09RNHV5dm94NjUKdG9TWGNac054dUs4QTErZXNXR3JSN3pVc0djdU9QQTFERE9Ja2JjcGtmRUxMNjk4RTJRckdqTU9JWnhrcWdxZQoySE5VNktWRmV2NzdZeEJDbm1VcVdXZEhYMjcyU2NPMUYzdWpUdFVnRVBNWGN0aEdBckYzTWxEaUw1Q0k0RkhqCnhHc3pVemxzalRQTmpiY2MzdUE2MjVZS3VVZEI2c1h1Rk5NUHk5UDgwTzBpRWJGTXl3MWxmN2VpdFhvaUUxWVoKc3NhMDVxTUx4M3pPUXZTLzFDdFpqaFp4cVJMRW5pQ3NWa2JVRlVYclpodEU4dG94bGpWSUtpQ25qbitORmtqdwo2bTZ1anpBSytZZHd2Nk5WMFB4S0gwUk5NYVhwb1lmQk1oUmZ3dGlaS3V3Y2hyRFB5UEhBQ2J3WXNZOXdtUE9rCnpwdDNxWi9JdDVYTmVqNDI0RzAzcGpMbk1sd1B1T1VzYmFQUWQ2VHU4TFhsckZReUVjTXJDNHdjUTA1SzFVN3kKM1NNN3RFaTlnbjV3RjY1YVI5eEFBR0grTUtMMk5WNnQrUmlTazJVaWs1clNmeDE4Mk9wYmpSQ2grdmQ4UXhJdwotLS0tLUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQo='  # noqa: E501
PRIVATE_KEY_PASSWORD = 'pwd1234'
PUBLIC_KEY_PEM_BASE64 = 'LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUF0dis3NlNXbklhOFFKWC94RUQxRQpYdnBBQmE3ajBnQnVYenJNUU5adjhtTW1RU0t2VUF0TmpOL2xacUZpQ0haZUQxU2VDcGV1MnFHTm5XbGRxNkhUCnh5cXJpTVZEbFNKaFBNT09QSENISVNVdFI4Tk5lR1Y1MU0wYkxJcENabHcyTU9GUjdqdENWejVqZFRpZ1NvYTIKQWxrRUlRZWQ4UVlDKzk1aGJoOHk5bGcwQ0JxdEdWN1FvMFZQR2xKQ0hGaWNuaWxLVFFZay9MZzkwWVFnUElPbwozbUppeFl5bWFGNmlMZTVXNzg1M0VHWUVFVWdlWmNaZFNjaGVBMEdBMGpRSFVTdnYvMEZjay9adkZNZURJOTVsCmJVQ0JoQjFDbFg4OG4wZUhzUmdWZE5vK0NLMDI4T2IvZTZTK1JLK09VaHlFRVdPTi90alVMdGhJdTJkQWtGcmkKOFFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=='  # noqa: E501
PRIVATE_KEY = load_private_key(PRIVATE_KEY_PEM_BASE64, PRIVATE_KEY_PASSWORD)
PUBLIC_KEY = _load_public_key(PUBLIC_KEY_PEM_BASE64)


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
    assert create_hmac_signature(secret_key, message) == 'FYMcmTIm3idXqleF1Sw5'
