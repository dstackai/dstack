import os
from base64 import b64decode, b64encode
from typing import Literal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import Field, validator
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.server.services.encryption.keys.base import EncryptionKey


class AESEncryptionKeyConfig(CoreModel):
    type: Annotated[Literal["aes"], Field(description="The type of the key")] = "aes"
    name: Annotated[str, Field(description="The key name for key identification")]
    secret: Annotated[str, Field(description="Base64-encoded AES-256 key")]

    @validator("name")
    def validate_name(cls, v):
        if not v.isalnum():
            raise ValueError("Key name must be alphanumeric")
        return v

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
        self.config = config
        self.key = b64decode(config.secret)

    @property
    def name(self) -> str:
        return self.config.name

    def encrypt(self, plaintext: str) -> str:
        # Generate a random 12-byte (96-bit) nonce (recommended size for GCM)
        nonce = os.urandom(12)

        # Create an AESGCM object and encrypt the plaintext
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

        # base64-encode the nonce and ciphertext for storage
        return b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        data = b64decode(ciphertext)

        # Extract the nonce and ciphertext
        nonce = data[:12]
        decoded_ciphertext = data[12:]

        # Create an AESGCM object and decrypt the ciphertext
        aesgcm = AESGCM(self.key)
        plaintext = aesgcm.decrypt(nonce, decoded_ciphertext, None)

        return plaintext.decode("utf-8")
