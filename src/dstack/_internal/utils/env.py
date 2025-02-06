import os


def get_bool(name: str, default: bool = False) -> bool:
    try:
        value = os.environ[name]
    except KeyError:
        return default
    value = value.lower()
    if value in ["0", "false", "off"]:
        return False
    if value in ["1", "true", "on"]:
        return True
    raise ValueError(f"Invalid bool value: {name}={value}")
