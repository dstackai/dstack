from abc import ABC, abstractmethod
from typing import ClassVar


class EncryptionKey(ABC):
    TYPE: ClassVar[str]

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def encrypt(self, plaintext: str) -> str:
        pass

    @abstractmethod
    def decrypt(self, ciphertext: str) -> str:
        pass
