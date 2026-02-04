from typing import Any, Optional, TypeVar, Union

from pydantic import BaseModel

from dstack._internal.core.models.common import CoreModel, IncludeExcludeType


class ModelFieldDiff(CoreModel):
    old: Any
    new: Any


ModelDiff = dict[str, Union[ModelFieldDiff, "ModelDiff"]]


# TODO: calculate nested diffs
def diff_models(
    old: BaseModel, new: BaseModel, reset: Optional[IncludeExcludeType] = None
) -> ModelDiff:
    """
    Returns a diff of model instances fields.

    The fields specified in the `reset` option are reset to their default values, effectively
    excluding them from comparison (assuming that the default value is equal to itself, e.g,
    `None == None`, `"task" == "task"`, but `math.nan != math.nan`).

    Args:
        old: The "old" model instance.
        new: The "new" model instance.
        reset: Fields to reset to their default values before comparison.

    Returns:
        A dict of changed fields in the form of
        `{<field_name>: {"old": old_value, "new": new_value}}`
    """
    if type(old) is not type(new):
        raise TypeError("Both instances must be of the same Pydantic model class.")

    if reset is not None:
        old = copy_model(old, reset=reset)
        new = copy_model(new, reset=reset)

    changes: ModelDiff = {}
    for field in old.__fields__:
        old_value = getattr(old, field)
        new_value = getattr(new, field)
        if old_value != new_value:
            changes[field] = ModelFieldDiff(old=old_value, new=new_value)

    return changes


M = TypeVar("M", bound=BaseModel)


def copy_model(model: M, reset: Optional[IncludeExcludeType] = None) -> M:
    """
    Returns a deep copy of the model instance.

    Implemented as `BaseModel.parse_obj(BaseModel.dict())`, thus,
    unlike `BaseModel.copy(deep=True)`, runs all validations.

    The fields specified in the `reset` option are reset to their default values.

    Args:
        reset: Fields to reset to their default values.

    Returns:
        A deep copy of the model instance.
    """
    return type(model).parse_obj(model.dict(exclude=reset))


def flatten_diff_fields(diff: ModelDiff, prefix: str = "") -> list[str]:
    """
    Recursively collects all field paths from a diff.

    Returns:
        A list of field paths, each path with dot-separated parts.
    """
    fields = []
    for field_name, field_diff in diff.items():
        current_path = f"{prefix}.{field_name}" if prefix else field_name

        if isinstance(field_diff, ModelFieldDiff):
            fields.append(current_path)
        else:
            fields.extend(flatten_diff_fields(field_diff, current_path))

    return fields


def format_diff_fields_for_event(diff: ModelDiff) -> str:
    return ", ".join(flatten_diff_fields(diff))
