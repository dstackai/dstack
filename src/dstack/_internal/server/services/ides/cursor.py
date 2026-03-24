from typing import Optional

from dstack._internal.server.services.ides.base import IDE


class CursorDesktop(IDE):
    name = "Cursor"
    url_scheme = "cursor"

    def get_install_commands(
        self, version: Optional[str] = None, extensions: Optional[list[str]] = None
    ) -> list[str]:
        commands = []
        if version is not None:
            url = f"https://cursor.blob.core.windows.net/remote-releases/{version}/vscode-reh-linux-$arch.tar.gz"
            archive = "vscode-reh-linux-$arch.tar.gz"
            target = f'~/.cursor-server/cli/servers/"Stable-{version}"/server'
            commands.extend(
                [
                    'if [ $(uname -m) = "aarch64" ]; then arch="arm64"; else arch="x64"; fi',
                    "mkdir -p /tmp",
                    f'wget -q --show-progress "{url}" -O "/tmp/{archive}"',
                    f"mkdir -vp {target}",
                    f'tar --no-same-owner -xz --strip-components=1 -C {target} -f "/tmp/{archive}"',
                    f'rm "/tmp/{archive}"',
                ]
            )
            if extensions:
                _extensions = " ".join(f'--install-extension "{name}"' for name in extensions)
                commands.append(f'PATH="$PATH":{target}/bin cursor-server {_extensions}')
        return commands
