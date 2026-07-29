"""
Fixture comparison for the pydantic v1 → v2 migration.

Fixtures are generated under pydantic v1 and committed. The same tests then run under v2, so a
mismatch means the two versions disagree about the wire format. Regenerating a fixture IS the act
of accepting a wire change — every accepted diff shows up in review as a fixture diff.

Layout is `fixtures/<direction>/<surface>/<model>[.<variant>].<role>`:

- direction: `serialization` or `parsing`
- surface: `db`, `api_request`, `api_response`, `config`
- variant: omitted while a model has only one case; added to *every* case for that model as soon
  as a second one exists, so `volume.input.yml` becomes `volume.size.input.yml` and
  `volume.kubernetes.input.yml` together
- role: `input` for hand-written parse inputs, `values` / `types` for generated expectations, and
  a bare `.json` for serialization fixtures, which need no input
"""

import difflib
import json
from pathlib import Path
from typing import Any, Union

import pytest
from pydantic import BaseModel

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Types JSON represents faithfully. Anything else — a `Duration` (int subclass), a `Memory`
# (float subclass), an enum, or a model standing in for a union arm — renders identically to its
# base type, so the value dump cannot show which one parsing produced.
_JSON_NATIVE = (str, int, float, bool, type(None))

_REGEN_HINT = (
    "Fix the regression, or if the change is intended, accept it with"
    " `pytest src/tests/_internal/pydantic_compat --regen-fixtures`."
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


def type_map(value: Any, path: str = "", out: Union[dict, None] = None) -> dict:
    """
    Map JSON pointer -> the concrete class parsing produced, wherever JSON erases it.

    `Duration(7200)` and `7200` serialize identically, as do `Memory(16.0)` and `16.0`, and
    `PythonVersion.PY310` and `"3.10"`. Losing the subclass is therefore invisible in the value
    dump while still being a real regression — `Memory.__str__` is `"16GB"`, and that string
    reaches the CLI. Models are recorded as well as recursed into, so a union that resolves to a
    different arm shows up here even when both arms happen to serialize the same.
    """
    out = {} if out is None else out
    if isinstance(value, BaseModel):
        out[path or "/"] = _class_name(value)
        for name, attr in value.__dict__.items():
            type_map(attr, f"{path}/{name}", out)
    elif isinstance(value, dict):
        for key, attr in value.items():
            type_map(attr, f"{path}/{key}", out)
    elif isinstance(value, (list, tuple)):
        for i, attr in enumerate(value):
            type_map(attr, f"{path}/{i}", out)
    elif type(value) not in _JSON_NATIVE:
        out[path] = _class_name(value)
    return out


def _class_name(value: Any) -> str:
    """
    The model's name with pydantic-duality's generated suffix removed.

    Duality names its concrete classes `XRequest` / `XResponse`, and those suffixes vanish in v2,
    so leaving them in would make every line of every type map diff on the migration branch.

    Strip only for classes duality actually generated, which is what `__response__` identifies.
    Plenty of models are genuinely *named* `...Request` — every gateway registry schema, for one —
    and those are plain `BaseModel`, so stripping there would report `RegisterService` for a class
    called `RegisterServiceRequest`.
    """
    cls = type(value)
    name = cls.__name__
    if hasattr(cls, "__response__"):
        for suffix in ("Request", "Response"):
            name = name.removesuffix(suffix)
    return name
