from typing import List

from dstack._internal.configurators.extensions import CommandsExtension


def require(executables: List[str]) -> CommandsExtension:
    def wrapper(commands: List[str]):
        for exe in executables:
            commands.append(
                f'((command -v {exe} > /dev/null) || (echo "{exe} is required" && exit 1))'
            )

    return wrapper
