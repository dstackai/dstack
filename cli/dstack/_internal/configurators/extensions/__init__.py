from abc import ABC, abstractmethod
from typing import List


class IDEExtension(ABC):
    @abstractmethod
    def get_install_commands(self) -> List[str]:
        pass

    @abstractmethod
    def get_install_if_not_found_commands(self) -> List[str]:
        pass

    @abstractmethod
    def get_print_readme_commands(self) -> List[str]:
        pass
