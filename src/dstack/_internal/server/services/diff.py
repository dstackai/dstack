from typing import Any, Dict

from pydantic import BaseModel


# TODO: calculate nested diffs
def diff_models(old: BaseModel, new: BaseModel) -> Dict[str, Any]:
    if type(old) is not type(new):
        raise TypeError("Both instances must be of the same Pydantic model class.")

    changes = {}
    for field in old.__fields__:
        old_value = getattr(old, field)
        new_value = getattr(new, field)
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}

    return changes
