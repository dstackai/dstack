from typing import Any, Optional, TypedDict

from pydantic import BaseModel

from dstack._internal.core.models.common import IncludeExcludeType


class ModelFieldDiff(TypedDict):
    old: Any
    new: Any


ModelDiff = dict[str, ModelFieldDiff]


# TODO: calculate nested diffs
def diff_models(
    old: BaseModel, new: BaseModel, ignore: Optional[IncludeExcludeType] = None
) -> ModelDiff:
    """
    Returns a diff of model instances fields.

    NOTE: `ignore` is implemented as `BaseModel.parse_obj(BaseModel.dict(exclude=ignore))`,
    that is, the "ignored" fields are actually not ignored but reset to the default values
    before comparison, meaning that 1) any field in `ignore` must have a default value,
    2) the default value must be equal to itself (e.g. `math.nan` != `math.nan`).

    Args:
        old: The "old" model instance.
        new: The "new" model instance.
        ignore: Optional fields to ignore.

    Returns:
        A dict of changed fields in the form of
        `{<field_name>: {"old": old_value, "new": new_value}}`
    """
    if type(old) is not type(new):
        raise TypeError("Both instances must be of the same Pydantic model class.")

    if ignore is not None:
        old = type(old).parse_obj(old.dict(exclude=ignore))
        new = type(new).parse_obj(new.dict(exclude=ignore))

    changes: ModelDiff = {}
    for field in old.__fields__:
        old_value = getattr(old, field)
        new_value = getattr(new, field)
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}

    return changes
