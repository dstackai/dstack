from typing import Optional

from dstack._internal.server.services.ides.base import IDE


class ZedDesktop(IDE):
    name = "Zed"
    url_scheme = "zed"

    def get_install_commands(
        self, version: Optional[str] = None, extensions: Optional[list[str]] = None
    ) -> list[str]:
        # We don't need to pre-install any extensions for Zed so we let it
        # auto-install the remote server into ~/.zed_server on the first SSH connect,
        # downloading the binary that matches the connecting Zed client version.
        return []

    def get_url(self, authority: str, working_dir: str) -> str:
        return f"zed://ssh/{authority}{working_dir}"
