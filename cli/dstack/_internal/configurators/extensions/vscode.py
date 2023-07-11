import subprocess
from typing import List, Optional

from dstack._internal.cli.common import console
from dstack._internal.configurators.extensions import IDEExtension


class VSCodeDesktop(IDEExtension):
    def __init__(
        self, extensions: List[str], version: Optional[str] = None, run_name: Optional[str] = None
    ):
        self.extensions = extensions
        if version is None:
            version = self.detect_code_version()
        if version is None:
            console.print(
                "[grey58]Unable to detect the VS Code version and pre-install extensions. "
                "Fix by opening [sea_green3]Command Palette[/sea_green3], executing [sea_green3]Shell Command: "
                "Install 'code' command in PATH[/sea_green3], and restarting terminal.[/]\n"
            )
        self.version = version
        self.run_name = run_name

    @classmethod
    def detect_code_version(cls, exe: str = "code") -> Optional[str]:
        try:
            run = subprocess.run([exe, "--version"], capture_output=True)
        except FileNotFoundError:
            return None
        if run.returncode == 0:
            return run.stdout.decode().split("\n")[1].strip()
        return None

    def install(self, commands: List[str]):
        if self.version is None:
            return
        url = (
            f"https://update.code.visualstudio.com/commit:{self.version}/server-linux-$arch/stable"
        )
        archive = "vscode-server-linux-$arch.tar.gz"
        target = f'~/.vscode-server/bin/"{self.version}"'
        commands.extend(
            [
                f'if [ $(uname -m) = "aarch64" ]; then arch="arm64"; else arch="x64"; fi',
                f"mkdir -p /tmp",
                f'wget -q --show-progress "{url}" -O "/tmp/{archive}"',
                f"mkdir -vp {target}",
                f'tar --no-same-owner -xz --strip-components=1 -C {target} -f "/tmp/{archive}"',
                f'rm "/tmp/{archive}"',
            ]
        )
        if self.extensions:
            extensions = " ".join(f'--install-extension "{name}"' for name in self.extensions)
            commands.append(f'PATH="$PATH":{target}/bin code-server {extensions}')

    def install_if_not_found(self, commands: List[str]):
        if self.version is None:
            return
        install_commands = []
        self.install(install_commands)
        install_commands = " && ".join(install_commands)
        commands.append(
            f'if [ ! -d ~/.vscode-server/bin/"{self.version}" ]; then {install_commands}; fi'
        )

    def print_readme(self, commands: List[str]):
        commands.extend(
            [
                f"echo To open in VS Code Desktop, use link below:",
                f"echo ''",
                f"echo '  vscode://vscode-remote/ssh-remote+{self.run_name}/workflow'",
                f"echo ''",
            ]
        )
