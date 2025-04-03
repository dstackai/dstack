from pathlib import Path


def fill_data(values: dict, filename_field: str = "filename", data_field: str = "data") -> dict:
    if values.get(data_field) is not None:
        return values
    if (filename := values.get(filename_field)) is None:
        raise ValueError(f"Either `{filename_field}` or `{data_field}` must be specified")
    try:
        with open(Path(filename).expanduser()) as f:
            values[data_field] = f.read()
    except OSError:
        raise ValueError(f"No such file {filename}")
    return values
