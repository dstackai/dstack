"""
Parse equality for stored blobs, request bodies, and client-side response parsing.

Each case is a frozen input plus two expectations: the values parsing produced, and the concrete
classes it chose. Both are needed — `Duration(7200)` and `7200` are the same JSON, so the value
fixture alone cannot show that a custom type survived.

Inputs are deliberately NOT canonical dumps. Feeding a model its own output back makes the
expected values identical to the input and the test proves nothing; every input here differs from
its output in some way a real writer could produce — an unknown field from a newer version, an
absent field that now defaults, or a sugared value.

Inputs are hand-written and must never be regenerated. `--regen-fixtures` rewrites
`*.values.json` and `*.types.json` only.
"""

import json
from typing import Any

import pytest

from dstack._internal.core.models.fleets import Fleet
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.server.schemas.volumes import CreateVolumeRequest
from tests._internal.pydantic_compat.compare import (
    FIXTURES_DIR,
    assert_matches_fixture,
    type_map,
)
from tests._internal.pydantic_compat.compat import parse_permissive, parse_strict

# Read from a `Text` column, permissively, so a row written by a newer server still loads.
DB_BLOBS: dict[str, Any] = {
    "run_spec": RunSpec,
}

# Validated from a request body, strictly: an unknown field is a user-facing error, not noise.
REQUEST_BODIES: dict[str, Any] = {
    "create_volume_request": CreateVolumeRequest,
}

# Parsed by the API client from a server response, permissively, so an older CLI works.
CLIENT_RESPONSES: dict[str, Any] = {
    "fleet": Fleet,
}


class TestDbBlobParsing:
    @pytest.mark.parametrize("name", sorted(DB_BLOBS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        _assert_parses(
            "db", name, parse_permissive(DB_BLOBS[name], _load_input("db", name)), regen
        )


class TestRequestBodyParsing:
    @pytest.mark.parametrize("name", sorted(REQUEST_BODIES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_strict(REQUEST_BODIES[name], _load_input("api_request", name))
        _assert_parses("api_request", name, model, regen)

    @pytest.mark.parametrize("name", sorted(REQUEST_BODIES))
    def test_unknown_field_is_still_rejected(self, name):
        """
        Strictness is the feature here: it is what makes `dstack apply` report a typo'd key
        instead of silently ignoring it. The v2 `CoreModel` is strict with a per-call
        `extra="ignore"` override, so the regression to guard against is that override leaking
        onto a request path.
        """
        body = {**_load_input("api_request", name), "definitely_not_a_field": 1}
        with pytest.raises(Exception, match="(?i)extra"):
            parse_strict(REQUEST_BODIES[name], body)


class TestClientResponseParsing:
    @pytest.mark.parametrize("name", sorted(CLIENT_RESPONSES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_permissive(CLIENT_RESPONSES[name], _load_input("api_response", name))
        _assert_parses("api_response", name, model, regen)


def _assert_parses(surface: str, name: str, model, regen: bool) -> None:
    kind = f"parsing/{surface}"
    assert_matches_fixture(kind, f"{name}.values", model.json(), regen=regen)
    assert_matches_fixture(kind, f"{name}.types", json.dumps(type_map(model)), regen=regen)


def _load_input(surface: str, name: str) -> Any:
    return json.loads((FIXTURES_DIR / "parsing" / surface / f"{name}.input.json").read_text())
