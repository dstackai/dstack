from abc import ABC, abstractmethod
from typing import ClassVar


class EncryptionKey(ABC):
    TYPE: ClassVar[str]

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        pass

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        pass
