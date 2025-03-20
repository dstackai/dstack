from pathlib import Path


def fill_data(values: dict):
    if values.get("data") is not None:
        return values
    if "filename" not in values:
        raise ValueError()
    try:
        with open(Path(values["filename"]).expanduser()) as f:
            values["data"] = f.read()
    except OSError:
        raise ValueError(f"No such file {values['filename']}")
    return values
