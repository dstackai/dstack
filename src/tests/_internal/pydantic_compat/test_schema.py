"""
The two JSON Schemas dstack publishes.

`generate-json-schema` in `.github/workflows/build-artifacts.yml` renders exactly these two, and
`upload-post-pypi-artifacts.yml` copies them to `s3://dstack-runner-downloads/<version>/schemas/`
and `latest/schemas/`. Editor YAML plugins fetch them from there to validate `.dstack.yml` and
`profiles.yml`, which makes the schema a published format with consumers outside this repo rather
than an internal detail — and unlike the other surfaces here, nothing in the codebase reads it
back, so a regression has no failing caller to reveal it.

pydantic v2 changes it on purpose: JSON Schema moves to draft 2020-12, so `definitions` becomes
`$defs`, `Optional[X]` renders as `anyOf: [..., {"type": "null"}]`, and a `$ref` with siblings
gets wrapped. The snapshot exists to make that diff explicit and reviewable in one place instead
of leaving it to a user whose editor quietly stopped validating.

The fixtures are canonicalized rather than byte-identical to the published files: sorted keys and
two-space indent, where CI emits one long line. Key order carries no meaning in JSON Schema, and a
3800-line reflow is not a diff anyone can review.
"""

import json
from typing import Any, Union

import pytest

from dstack._internal.core.models.configurations import DstackConfiguration
from dstack._internal.core.models.profiles import ProfilesConfig
from tests._internal.pydantic_compat.compare import assert_matches_fixture

# Keyed by the filename CI publishes, so the mapping to the S3 object is unambiguous.
PUBLISHED_SCHEMAS: dict[str, Any] = {
    "configuration": DstackConfiguration,
    "profiles": ProfilesConfig,
}


class TestPublishedSchemas:
    @pytest.mark.parametrize("name", sorted(PUBLISHED_SCHEMAS))
    def test_matches_fixture(self, name, regen):
        # The exact call the CI job makes.
        schema_json = PUBLISHED_SCHEMAS[name].schema_json()
        assert_matches_fixture("schema", name, schema_json, regen=regen)

    @pytest.mark.parametrize("name", sorted(PUBLISHED_SCHEMAS))
    def test_every_ref_resolves(self, name):
        """
        A dangling `$ref` makes the whole schema unusable to a validator, and the snapshot alone
        would not flag it — a broken ref is just another line in a 3800-line diff that gets
        accepted along with the intended draft change.

        This is not hypothetical: `add_extra_schema_types` in `utils/json_schema.py` rewrites
        properties in place and has already produced a `KeyError: '$ref'` in this job once.
        """
        schema = json.loads(PUBLISHED_SCHEMAS[name].schema_json())
        definitions = _definitions(schema)
        assert definitions, "expected the schema to define types to reference"
        unresolved = sorted(
            ref for ref in _collect_refs(schema) if _ref_target(ref) not in definitions
        )
        assert unresolved == []


def _definitions(schema: dict) -> dict:
    """v1 emits `definitions`, draft 2020-12 emits `$defs`. Accept whichever is present."""
    return schema.get("definitions") or schema.get("$defs") or {}


def _collect_refs(node: Any, out: Union[list, None] = None) -> list:
    out = [] if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            out.append(node["$ref"])
        for value in node.values():
            _collect_refs(value, out)
    elif isinstance(node, list):
        for value in node:
            _collect_refs(value, out)
    return out


def _ref_target(ref: str) -> str:
    """`#/definitions/Foo` or `#/$defs/Foo` -> `Foo`."""
    return ref.rsplit("/", 1)[-1]
