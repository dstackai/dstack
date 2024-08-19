from contextlib import contextmanager
from typing import List, Tuple, Union

from dstack._internal.core.errors import DstackError
from dstack._internal.server.models import EncryptedString
from dstack._internal.server.services.encryption.keys.aes import (
    AESEncryptionKey,
    AESEncryptionKeyConfig,
)
from dstack._internal.server.services.encryption.keys.base import EncryptionKey
from dstack._internal.server.services.encryption.keys.identity import (
    IdentityEncryptionKey,
    IdentityEncryptionKeyConfig,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class EncryptionError(DstackError):
    pass


AnyEncryptionKeyConfig = Union[
    AESEncryptionKeyConfig,
    IdentityEncryptionKeyConfig,
]


_ENCRYPTION_KEY_CLASSES = [
    IdentityEncryptionKey,
    AESEncryptionKey,
]
_ENCRYPTION_KEY_TYPE_TO_ENCRYPTION_KEY_CLASS = {c.TYPE: c for c in _ENCRYPTION_KEY_CLASSES}


# TODO: Introduce EncryptionKeyConfigurator to support external providers
def get_encryption_key(config: AnyEncryptionKeyConfig) -> EncryptionKey:
    return _ENCRYPTION_KEY_TYPE_TO_ENCRYPTION_KEY_CLASS[config.type](config)


def get_identity_encryption_key() -> IdentityEncryptionKey:
    return IdentityEncryptionKey(IdentityEncryptionKeyConfig())


_encryption_keys = [get_identity_encryption_key()]


def init_encryption_keys(encryption_key_configs: List[AnyEncryptionKeyConfig]):
    global _encryption_keys
    _encryption_keys = [get_encryption_key(c) for c in encryption_key_configs]
    if not any(isinstance(key, IdentityEncryptionKey) for key in _encryption_keys):
        _encryption_keys.append(get_identity_encryption_key())


@contextmanager
def encryption_keys_context(encryption_keys: List[EncryptionKey]):
    """
    A helper context manager to be used in tests. It's not concurrency-safe.
    """
    global _encryption_keys
    prev_encryption_keys = _encryption_keys
    _encryption_keys = encryption_keys
    try:
        yield
    finally:
        _encryption_keys = prev_encryption_keys


def encrypt(plaintext: str) -> str:
    key = _encryption_keys[0]
    ciphertext = key.encrypt(plaintext)
    packed_ciphertext = _pack_ciphertext(ciphertext, key_type=key.TYPE, key_name=key.name)
    return packed_ciphertext


def decrypt(ciphertext: str) -> str:
    key_type, _, ciphertext = _unpack_ciphertext(ciphertext)
    # Ignore key_name when decrypting
    for i, key in enumerate(_encryption_keys):
        if key.TYPE != key_type:
            continue
        try:
            return key.decrypt(ciphertext)
        except Exception:
            logger.debug(f"Attempt to decrypt ciphertext with key #{i} failed")
    raise EncryptionError("All keys failed to decrypt ciphertext")


def _pack_ciphertext(ciphertext: str, key_type: str, key_name: str) -> str:
    return f"enc:{key_type}:{key_name}:{ciphertext}"


def _unpack_ciphertext(packed_ciphertext: str) -> Tuple[str, str, str]:
    _, key_type, key_name, ciphertext = packed_ciphertext.split(":", maxsplit=3)
    return key_type, key_name, ciphertext


EncryptedString.set_encrypt_decrypt(
    encrypt_func=encrypt,
    decrypt_func=decrypt,
)
