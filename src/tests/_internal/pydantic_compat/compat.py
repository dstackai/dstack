"""
The one place in this package that knows how each `extra` mode is spelled.

Every test here was written to run unchanged on v1 and v2, which ruled out touching the duality
API directly. Forbidding extra fields needs no help — `model_validate` forbids them in both
versions. Ignoring them did: v1 spelled it `X.__response__`, and v2 spells it
`validate_extra_ignore`.

Both helpers are named for the `extra` setting they apply, deliberately avoiding the word
"strict": pydantic's `strict` is an unrelated axis that turns off type coercion, and a migration
that may well want real strict mode later should not have the term already spent on something
else.
"""

from typing import Any

from pydantic import BaseModel

from dstack._internal.core.models.common import validate_extra_ignore


def parse_forbid_extra(model: Any, data: Any) -> BaseModel:
    """
    Parse with `extra="forbid"` — the way the server validates a request body or a user's YAML.

    An unknown field is an error, which is what makes `dstack apply` report a typo'd key instead
    of silently ignoring it.
    """
    return model.model_validate(data)


def parse_ignore_extra(model: Any, data: Any) -> BaseModel:
    """
    Parse with `extra="ignore"` — the way a stored blob or a peer's response is read.

    Unknown fields are dropped, which is what lets an older reader survive a newer writer, so it
    is the behaviour the whole migration has to preserve.
    """
    # Works for plain `BaseModel` too (the proxy and gateway schemas, whose default is already
    # extra="ignore"): the per-call override applies to any model, not just `CoreModel`.
    return validate_extra_ignore(model, data)
