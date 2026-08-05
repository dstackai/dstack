from pathlib import Path
from typing import List, TypeVar

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.runs import Job
from dstack._internal.core.models.volumes import Volume


class JobConfiguration(CoreModel):
    job: Job
    volumes: List[Volume]


M = TypeVar("M", bound=CoreModel)


def fill_data(model: M, filename_field: str = "filename", data_field: str = "data") -> M:
    """
    Reads `data_field` from the file at `filename_field` unless it is already set.

    Call from an `after` validator: the fields must be validated already, or a malformed
    `filename_field` reaches `open()` as-is and raises `TypeError` instead of a validation error.
    """
    if getattr(model, data_field) is not None:
        return model
    filename = getattr(model, filename_field)
    # An unset path field defaults to `""` in some configs and to `None` in others.
    if not filename:
        raise ValueError(f"Either `{filename_field}` or `{data_field}` must be specified")
    try:
        with open(Path(filename).expanduser()) as f:
            setattr(model, data_field, f.read())
    except OSError:
        raise ValueError(f"No such file {filename}")
    return model
