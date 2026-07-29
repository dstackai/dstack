"""
Fixture comparison for the pydantic v1 → v2 migration.

Fixtures are generated under pydantic v1 and committed. The same tests then run under v2, so a
mismatch means the two versions disagree about the wire format. Regenerating a fixture IS the act
of accepting a wire change — every accepted diff shows up in review as a fixture diff.
"""

import difflib
import json
from pathlib import Path
from typing import Union

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_REGEN_HINT = (
    "Fix the regression, or if the change is intended, accept it with"
    " `pytest src/tests/_internal/pydantic_compat --regen-wire-fixtures`."
)


def canonicalize(payload: Union[bytes, str]) -> str:
    """
    Re-render a JSON payload so that only meaningful differences survive.

    `sort_keys` drops key-order noise, which the v2 serializer is free to change.

    Comparing the re-rendered *text* rather than the parsed objects is deliberate: `==` on parsed
    JSON would miss the drift this suite exists to catch, because Python compares `16 == 16.0` and
    `True == 1` as equal. `Memory` is a `float` subclass and `Duration` an `int` subclass, so an
    int/float representation change is one of the likeliest v2 diffs — and `json.dumps` renders
    `16` and `16.0` distinctly where `==` cannot tell them apart.
    """
    return json.dumps(json.loads(payload), indent=2, sort_keys=True) + "\n"


def assert_matches_fixture(kind: str, name: str, payload: Union[bytes, str], regen: bool) -> None:
    """Compare a serialized payload against `fixtures/<kind>/<name>.json`."""
    path = FIXTURES_DIR / kind / f"{name}.json"
    actual = canonicalize(payload)

    if regen:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(actual)
        return

    if not path.exists():
        pytest.fail(f"no fixture at {path.relative_to(FIXTURES_DIR.parent)}. {_REGEN_HINT}")

    expected = path.read_text()
    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                actual.splitlines(keepends=True),
                fromfile=f"{kind}/{name}.json (committed)",
                tofile=f"{kind}/{name}.json (actual)",
            )
        )
        pytest.fail(f"{kind}/{name} serialization changed:\n{diff}\n{_REGEN_HINT}")
