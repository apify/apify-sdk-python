from __future__ import annotations

import base64
import hashlib
import hmac
import json
import string
from typing import Any

from cryptography.exceptions import InvalidTag as InvalidTagException
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from crawlee._utils.crypto import crypto_random_object_id

from apify._consts import ENCRYPTED_INPUT_VALUE_REGEXP, ENCRYPTED_JSON_VALUE_PREFIX, ENCRYPTED_STRING_VALUE_PREFIX

ENCRYPTION_KEY_LENGTH = 32
ENCRYPTION_IV_LENGTH = 16
ENCRYPTION_AUTH_TAG_LENGTH = 16


def public_encrypt(value: str, *, public_key: rsa.RSAPublicKey) -> dict:
    """Encrypts the given value using AES cipher and the password for encryption using the public key.

    The encryption password is a string of encryption key and initial vector used for cipher.
    It returns the encrypted password and encrypted value in BASE64 format.

    Args:
        value: The value which should be encrypted.
        public_key: Public key to use for encryption.

    Returns: Encrypted password and value.
    """
    key_bytes = crypto_random_object_id(ENCRYPTION_KEY_LENGTH).encode('utf-8')
    initialized_vector_bytes = crypto_random_object_id(ENCRYPTION_IV_LENGTH).encode('utf-8')
    value_bytes = value.encode('utf-8')

    password_bytes = key_bytes + initialized_vector_bytes

    # NOTE: Auth Tag is appended to the end of the encrypted data, it has length of 16 bytes and ensures integrity
    # of the data.
    cipher = Cipher(
        algorithms.AES(key_bytes),
        modes.GCM(
            initialized_vector_bytes,
            min_tag_length=ENCRYPTION_AUTH_TAG_LENGTH,
        ),
    )
    encryptor = cipher.encryptor()
    encrypted_value_bytes = encryptor.update(value_bytes) + encryptor.finalize()
    encrypted_password_bytes = public_key.encrypt(
        password_bytes,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )
    return {
        'encrypted_value': base64.b64encode(encrypted_value_bytes + encryptor.tag).decode('utf-8'),
        'encrypted_password': base64.b64encode(encrypted_password_bytes).decode('utf-8'),
    }


def private_decrypt(
    encrypted_password: str,
    encrypted_value: str,
    *,
    private_key: rsa.RSAPrivateKey,
) -> str:
    """Decrypts the given encrypted value using the private key and password.

    Args:
        encrypted_password: Password used to encrypt the private key encoded as base64 string.
        encrypted_value: Encrypted value to decrypt as base64 string.
        private_key: Private key to use for decryption.

    Returns: Decrypted value.
    """
    encrypted_password_bytes = base64.b64decode(encrypted_password.encode('utf-8'))
    encrypted_value_bytes = base64.b64decode(encrypted_value.encode('utf-8'))

    # Decrypt the password
    password_bytes = private_key.decrypt(
        encrypted_password_bytes,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )

    if len(password_bytes) != ENCRYPTION_KEY_LENGTH + ENCRYPTION_IV_LENGTH:
        raise ValueError('Decryption failed, invalid password length!')

    # Slice the encrypted into cypher and authentication tag
    authentication_tag_bytes = encrypted_value_bytes[-ENCRYPTION_AUTH_TAG_LENGTH:]
    encrypted_data_bytes = encrypted_value_bytes[: (len(encrypted_value_bytes) - ENCRYPTION_AUTH_TAG_LENGTH)]
    encryption_key_bytes = password_bytes[:ENCRYPTION_KEY_LENGTH]
    initialization_vector_bytes = password_bytes[ENCRYPTION_KEY_LENGTH:]

    try:
        cipher = Cipher(
            algorithms.AES(encryption_key_bytes), modes.GCM(initialization_vector_bytes, authentication_tag_bytes)
        )
        decryptor = cipher.decryptor()
        decipher_bytes = decryptor.update(encrypted_data_bytes) + decryptor.finalize()
    except InvalidTagException as exc:
        raise ValueError('Decryption failed, malformed encrypted value or password.') from exc
    except Exception:
        raise

    return decipher_bytes.decode('utf-8')


def load_private_key(private_key_file_base64: str, private_key_password: str) -> rsa.RSAPrivateKey:
    private_key = serialization.load_pem_private_key(
        base64.b64decode(private_key_file_base64.encode('utf-8')),
        password=private_key_password.encode('utf-8'),
    )
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise TypeError('Invalid private key.')

    return private_key


def _load_public_key(public_key_file_base64: str) -> rsa.RSAPublicKey:
    public_key = serialization.load_pem_public_key(base64.b64decode(public_key_file_base64.encode('utf-8')))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise TypeError('Invalid public key.')

    return public_key


def decrypt_input_secrets(private_key: rsa.RSAPrivateKey, input_data: Any) -> Any:
    """Decrypt input secrets."""
    if not isinstance(input_data, dict):
        return input_data

    for key, value in input_data.items():
        if isinstance(value, str):
            match = ENCRYPTED_INPUT_VALUE_REGEXP.fullmatch(value)
            if match:
                prefix = match.group(1)
                encrypted_password = match.group(3)
                encrypted_value = match.group(4)
                decrypted_value = private_decrypt(
                    encrypted_password,
                    encrypted_value,
                    private_key=private_key,
                )

                if prefix == ENCRYPTED_STRING_VALUE_PREFIX:
                    input_data[key] = decrypted_value
                elif prefix == ENCRYPTED_JSON_VALUE_PREFIX:
                    input_data[key] = json.loads(decrypted_value)

    return input_data


CHARSET = string.digits + string.ascii_letters


def encode_base62(num: int) -> str:
    """Encode the given number to base62."""
    if num == 0:
        return CHARSET[0]

    res = ''
    while num > 0:
        num, remainder = divmod(num, 62)
        res = CHARSET[remainder] + res
    return res


def create_hmac_signature(secret_key: str, message: str) -> str:
    """Generate an HMAC signature and encodes it using Base62. Base62 encoding reduces the signature length.

    HMAC signature is truncated to 30 characters to make it shorter.

    Args:
        secret_key: Secret key used for signing signatures.
        message: Message to be signed.

    Returns:
        Base62 encoded signature.
    """
    signature = hmac.new(secret_key.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()[:30]

    decimal_signature = int(signature, 16)

    return encode_base62(decimal_signature)
