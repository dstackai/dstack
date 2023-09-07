from pydantic import BaseModel


class Secret(BaseModel):
    name: str
    value: str

    def __str__(self) -> str:
        return f'Secret(name="{self.name}", value={"*"*len(self.value)})'
