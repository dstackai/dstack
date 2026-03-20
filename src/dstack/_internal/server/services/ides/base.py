from abc import ABC, abstractmethod
from typing import ClassVar, Optional


class IDE(ABC):
    name: ClassVar[str]
    url_scheme: ClassVar[str]

    @abstractmethod
    def get_install_commands(
        self, version: Optional[str] = None, extensions: Optional[list[str]] = None
    ) -> list[str]:
        pass

    def get_url(self, authority: str, working_dir: str) -> str:
        return f"{self.url_scheme}://vscode-remote/ssh-remote+{authority}{working_dir}"

    def get_print_readme_commands(self, authority: str) -> list[str]:
        url = self.get_url(authority, working_dir="$DSTACK_WORKING_DIR")
        return [
            f"echo 'To open in {self.name}, use link below:'",
            "echo",
            f'echo "  {url}"',
            "echo",
        ]
