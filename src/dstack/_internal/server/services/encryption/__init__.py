from typing import List, Tuple, Union

from dstack._internal.core.errors import DstackError
from dstack._internal.server.models import set_decrypt_func, set_encrypt_func
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


def set_encryption_keys(encryption_key_configs: List[AnyEncryptionKeyConfig]):
    global _encryption_keys
    _encryption_keys = [get_encryption_key(c) for c in encryption_key_configs]
    if not any(isinstance(key, IdentityEncryptionKey) for key in _encryption_keys):
        _encryption_keys.append(get_identity_encryption_key())


def encrypt(plaintext: str) -> str:
    key = _encryption_keys[0]
    ciphertext = key.encrypt(plaintext)
    packed_ciphertext = pack_ciphertext(ciphertext, key_type=key.TYPE)
    return packed_ciphertext


def decrypt(ciphertext: str) -> str:
    key_type, ciphertext = unpack_ciphertext(ciphertext)
    for i, key in enumerate(_encryption_keys):
        if key.TYPE != key_type:
            continue
        try:
            return key.decrypt(ciphertext)
        except Exception:
            logger.debug(f"Attempt to decrypt ciphertext with key #{i} failed")
    raise EncryptionError("Failed to decrypt ciphertext")


def pack_ciphertext(ciphertext: str, key_type: str) -> str:
    return f"enc:{key_type}:{ciphertext}"


def unpack_ciphertext(packed_ciphertext: str) -> Tuple[str, str]:
    _, key_type, ciphertext = packed_ciphertext.split(":", maxsplit=2)
    return key_type, ciphertext


set_encrypt_func(encrypt)
set_decrypt_func(decrypt)
