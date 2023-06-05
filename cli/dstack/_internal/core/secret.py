from pydantic import BaseModel


class Secret(BaseModel):
    secret_name: str
    secret_value: str

    def __str__(self) -> str:
        return (
            f'Secret(secret_name="{self.secret_name}", '
            f"secret_value_length={len(self.secret_value)})"
        )
