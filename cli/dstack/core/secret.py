class Secret:
    def __init__(self, secret_name: str, secret_value: str):
        self.secret_name = secret_name
        self.secret_value = secret_value

    def __str__(self) -> str:
        return (
            f'Secret(secret_name="{self.secret_name}", '
            f"secret_value_length={len(self.secret_value)})"
        )
