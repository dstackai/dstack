"""
The only place in this package allowed to branch on pydantic version.

Every test here has to run unchanged on v1 and v2, which rules out touching the duality API
directly. Forbidding extra fields needs no help — `parse_obj` forbids them in both versions.
Ignoring them does: v1 spells it `X.__response__`, and v2 will spell it `validate_extra_ignore`.

Both helpers are named for the `extra` setting they apply, deliberately avoiding the word
"strict": pydantic's `strict` is an unrelated axis that turns off type coercion, and a migration
that may well want real strict mode later should not have the term already spent on something
else.
"""

from typing import Any

import pydantic
from pydantic import BaseModel

PYDANTIC_V1 = pydantic.VERSION.startswith("1.")


def parse_forbid_extra(model: Any, data: Any) -> BaseModel:
    """
    Parse with `extra="forbid"` — the way the server validates a request body or a user's YAML.

    An unknown field is an error, which is what makes `dstack apply` report a typo'd key instead
    of silently ignoring it.
    """
    return model.parse_obj(data)


def parse_ignore_extra(model: Any, data: Any) -> BaseModel:
    """
    Parse with `extra="ignore"` — the way a stored blob or a peer's response is read.

    Unknown fields are dropped, which is what lets an older reader survive a newer writer, so it
    is the behaviour the whole migration has to preserve.
    """
    if not hasattr(model, "__response__"):
        # Plain `BaseModel` rather than `CoreModel` — the proxy and gateway schemas. Their default
        # is already extra="ignore" in both pydantic versions, so `parse_obj` is the ignore path
        # and there is no duality variant to reach for.
        return model.parse_obj(data)
    if PYDANTIC_V1:
        return model.__response__.parse_obj(data)
    # v2: from dstack._internal.core.models.common import validate_extra_ignore
    raise NotImplementedError("wire up validate_extra_ignore when the v2 branch lands")
