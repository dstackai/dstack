from typing import Callable, List

CommandsExtension = Callable[[], List[str]]


def get_required_commands(executables: List[str]) -> CommandsExtension:
    def wrapper() -> List[str]:
        commands = []
        for exe in executables:
            commands.append(
                f'((command -v {exe} > /dev/null) || (echo "{exe} is required" && exit 1))'
            )
        return commands

    return wrapper
