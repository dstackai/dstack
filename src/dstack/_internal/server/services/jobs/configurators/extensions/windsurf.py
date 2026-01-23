from typing import List, Optional


class WindsurfDesktop:
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
            version, commit = self.version.split("@")
            url = f"https://windsurf-stable.codeiumdata.com/linux-reh-$arch/stable/{commit}/windsurf-reh-linux-$arch-{version}.tar.gz"
            archive = "windsurf-reh-linux-$arch.tar.gz"
            target = f'~/.windsurf-server/bin/"{commit}"'
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
                commands.append(f'PATH="$PATH":{target}/bin windsurf-server {extensions}')
        return commands

    def get_print_readme_commands(self) -> List[str]:
        return [
            "echo To open in Windsurf, use link below:",
            "echo",
            f'echo "  windsurf://vscode-remote/ssh-remote+{self.run_name}$DSTACK_WORKING_DIR"',
            "echo",
        ]
