from typing import List


class JetBrainsFleet:
    def __init__(self, run_name: str):
        self.run_name = run_name

    def get_install_commands(self) -> List[str]:
        commands = [
            f'if [ $(uname -m) = "aarch64" ]; then arch="aarch64"; else arch="x64"; fi',
            'wget -q --show-progress -O fleet "https://download.jetbrains.com/product?code=FLL&release.type=preview&release.type=eap&platform=linux_$arch" && chmod +x fleet',
            f"./fleet launch workspace -- --auth=accept-everyone --publish --workspaceName {self.run_name} --projectDir /workflow",
        ]
        return commands

    def get_print_readme_commands(self) -> List[str]:
        return []
