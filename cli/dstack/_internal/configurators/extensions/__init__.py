from abc import ABC, abstractmethod
from typing import Callable, List

CommandsExtension = Callable[[List[str]], None]


class IDEExtension(ABC):
    @abstractmethod
    def install(self, commands: List[str]):
        pass

    @abstractmethod
    def install_if_not_found(self, commands: List[str]):
        pass

    @abstractmethod
    def print_readme(self, commands: List[str]):
        pass
