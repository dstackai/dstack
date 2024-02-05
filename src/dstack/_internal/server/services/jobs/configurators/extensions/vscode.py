from typing import List


class VSCodeDesktop:
    def __init__(
        self,
        run_name: str,
        version: str,
        extensions: List[str],
    ):
        self.run_name = run_name
        self.version = version
        self.extensions = extensions

    def get_install_commands(self) -> List[str]:
        commands = []
        if self.version is not None:
            url = f"https://update.code.visualstudio.com/commit:{self.version}/server-linux-$arch/stable"
            archive = "vscode-server-linux-$arch.tar.gz"
            target = f'~/.vscode-server/bin/"{self.version}"'
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
                commands.append(f'PATH="$PATH":{target}/bin code-server {extensions}')
        return commands

    def get_print_readme_commands(self) -> List[str]:
        return [
            "echo To open in VS Code Desktop, use link below:",
            "echo ''",
            f"echo '  vscode://vscode-remote/ssh-remote+{self.run_name}/workflow'",  # TODO use $REPO_DIR
            "echo ''",
        ]
