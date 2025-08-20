from typing import List, Optional

from dstack._internal.core.models.configurations import DEFAULT_REPO_DIR


class CursorDesktop:
    def __init__(
        self,
        run_name: Optional[str],
        version: Optional[str],
        extensions: List[str],
    ):
        self.run_name = run_name
        self.version = version
        self.extensions = extensions

    def get_install_commands(self) -> List[str]:
        commands = []
        if self.version is not None:
            url = f"https://cursor.blob.core.windows.net/remote-releases/{self.version}/vscode-reh-linux-$arch.tar.gz"
            archive = "vscode-reh-linux-$arch.tar.gz"
            target = f'~/.cursor-server/cli/servers/"Stable-{self.version}"/server'
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
            if self.extensions:
                extensions = " ".join(f'--install-extension "{name}"' for name in self.extensions)
                commands.append(f'PATH="$PATH":{target}/bin cursor-server {extensions}')
        return commands

    def get_print_readme_commands(self) -> List[str]:
        return [
            "echo To open in Cursor, use link below:",
            "echo ''",
            f"echo '  cursor://vscode-remote/ssh-remote+{self.run_name}{DEFAULT_REPO_DIR}'",  # TODO use $REPO_DIR
            "echo ''",
        ]
