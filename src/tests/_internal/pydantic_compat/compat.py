"""
The only place in this package allowed to branch on pydantic version.

Every test here has to run unchanged on v1 and v2, which rules out touching the duality API
directly. Strict parsing needs no help — `parse_obj` is strict in both versions. Permissive
parsing does: v1 spells it `X.__response__`, and v2 will spell it `validate_extra_ignore`.
"""

from typing import Any

import pydantic
from pydantic import BaseModel

PYDANTIC_V1 = pydantic.VERSION.startswith("1.")


def parse_strict(model: Any, data: Any) -> BaseModel:
    """Parse the way the server validates a request body: unknown fields are an error."""
    return model.parse_obj(data)


def parse_permissive(model: Any, data: Any) -> BaseModel:
    """
    Parse the way a stored blob or a peer's response is read: unknown fields are ignored.

    This is what lets an older reader survive a newer writer, so it is the behaviour the whole
    migration has to preserve.
    """
    if PYDANTIC_V1:
        return model.__response__.parse_obj(data)
    # v2: from dstack._internal.core.models.common import validate_extra_ignore
    raise NotImplementedError("wire up validate_extra_ignore when the v2 branch lands")
