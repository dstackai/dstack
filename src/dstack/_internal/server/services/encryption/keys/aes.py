import os
from base64 import b64decode, b64encode
from typing import Literal

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pydantic import Field, validator
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.server.services.encryption.keys.base import EncryptionKey


class AESEncryptionKeyConfig(CoreModel):
    type: Literal["aes"] = "aes"
    secret: Annotated[str, Field(description="Base64-encoded AES-256 key")]

    @validator("secret")
    def validate_secret(cls, v):
        try:
            key = b64decode(v, validate=True)
        except Exception as e:
            raise ValueError("Failed to decode secret from base64") from e
        if len(key) != 32:
            raise ValueError(f"AES key must be 32 bytes. Got {len(key)} bytes")
        return v


class AESEncryptionKey(EncryptionKey):
    TYPE = "aes"

    def __init__(self, config: AESEncryptionKeyConfig) -> None:
        self.key = b64decode(config.secret)

    def encrypt(self, plaintext: str) -> str:
        # Generate a random 16-byte (128-bit) IV
        iv = os.urandom(16)

        # Create AES-GCM Cipher object and encrypt
        cipher = Cipher(algorithms.AES(self.key), modes.GCM(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode("utf-8")) + encryptor.finalize()
        tag = encryptor.tag

        # base64-encode the IV, ciphertext, and tag for storage
        return b64encode(iv + ciphertext + tag).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        data = b64decode(ciphertext)

        # Extract the IV, ciphertext, and tag
        iv = data[:16]
        decoded_ciphertext = data[16:-16]
        tag = data[-16:]

        # Create AES-GCM Cipher object for decryption
        cipher = Cipher(algorithms.AES(self.key), modes.GCM(iv, tag), backend=default_backend())
        decryptor = cipher.decryptor()

        # Decrypt the ciphertext and return the plaintext
        plaintext = decryptor.update(decoded_ciphertext) + decryptor.finalize()
        return plaintext.decode("utf-8")
