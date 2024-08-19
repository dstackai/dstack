from typing import Literal

from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel
from dstack._internal.server.services.encryption.keys.base import EncryptionKey


class IdentityEncryptionKeyConfig(CoreModel):
    type: Annotated[Literal["identity"], Field(description="The type of the key")] = "identity"


class IdentityEncryptionKey(EncryptionKey):
    TYPE = "identity"

    def __init__(self, config: IdentityEncryptionKeyConfig) -> None:
        pass

    @property
    def name(self) -> str:
        return "noname"

    def encrypt(self, plaintext: str) -> str:
        return plaintext

    def decrypt(self, ciphertext: str) -> str:
        return ciphertext
