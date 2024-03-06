from dstack._internal.core.models.common import CoreModel


class Secret(CoreModel):
    name: str
    value: str

    def __str__(self) -> str:
        return f'Secret(name="{self.name}", value={"*"*len(self.value)})'
