from abc import ABC, abstractmethod
from typing import Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound="BaseHead")


class BaseHead(BaseModel, ABC):
    @classmethod
    @abstractmethod
    def prefix(cls) -> str:
        pass

    def encode(self) -> str:
        tokens = []
        data = self.dict(exclude_none=True)
        for key in self.__fields__.keys():
            # replace missing with empty token
            tokens.append(str(data.get(key, "")))
        return self.prefix() + ";".join(tokens)

    @classmethod
    def decode(cls: Type[T], key: str) -> T:
        # maxsplit allows *args as last field
        values = key[len(cls.prefix()) :].split(";", maxsplit=len(cls.__fields__) - 1)
        # dict in python3 is ordered, map values to field names
        return cls.parse_obj(dict(zip(cls.__fields__.keys(), values)))
