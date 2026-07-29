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
import yaml

from dstack._internal.core.backends.aws.models import AWSCreds
from dstack._internal.core.models.configurations import DstackConfiguration
from dstack._internal.core.models.fleets import Fleet
from dstack._internal.core.models.profiles import ProfilesConfig
from dstack._internal.core.models.runs import JobSpec, RunSpec
from dstack._internal.proxy.gateway.schemas.registry import (
    RegisterReplicaRequest,
    RegisterServiceRequest,
)
from dstack._internal.server.schemas.runner import HealthcheckResponse, MetricsResponse
from dstack._internal.server.schemas.volumes import CreateVolumeRequest
from tests._internal.pydantic_compat.compare import (
    FIXTURES_DIR,
    assert_matches_fixture,
    canonicalize,
    type_map,
)
from tests._internal.pydantic_compat.compat import parse_forbid_extra, parse_ignore_extra
from tests._internal.pydantic_compat.test_serialization import DB_BLOBS as SERIALIZED_DB_BLOBS

# Read from a `Text` column with extra="ignore", so a row written by a newer server loads.
DB_BLOBS: dict[str, Any] = {
    "aws_creds": AWSCreds,
    "job_spec": JobSpec,
    "run_spec": RunSpec,
}

# Validated from a request body with extra="forbid": an unknown field is a user-facing error.
REQUEST_BODIES: dict[str, Any] = {
    "create_volume_request": CreateVolumeRequest,
}

# Parsed by the API client from a server response with extra="ignore", so an older CLI works.
CLIENT_RESPONSES: dict[str, Any] = {
    "fleet": Fleet,
}

# Parsed from user-authored YAML with extra="forbid". The only surface whose inputs are `.yml`,
# because the sugar pinned here is a YAML phenomenon: `python: 3.10` is a float that only survives via
# number->str coercion, and `16GB..` / `2..8` / an env list are shorthands people type by hand.
# `DstackConfiguration` dispatches every `.dstack.yml` type through its `__root__` union, so one
# entry point covers task, service, dev-environment, fleet, volume, and gateway.
CONFIGS: dict[str, Any] = {
    "fleet": DstackConfiguration,
    "profiles": ProfilesConfig,
    "service": DstackConfiguration,
    "task": DstackConfiguration,
    "volume": DstackConfiguration,
}


class TestDbBlobParsing:
    @pytest.mark.parametrize("name", sorted(DB_BLOBS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        _assert_parses(
            "db", name, parse_ignore_extra(DB_BLOBS[name], _load_input("db", name)), regen
        )


# Responses the server reads back from the runner (shim), permissively: a newer runner may add
# fields, and the server has no say over which runner version an instance is running.
RUNNER_RESPONSES: dict[str, Any] = {
    "healthcheck_response": HealthcheckResponse,
    "metrics_response": MetricsResponse,
}

# Request payloads the gateway parses from the server. These schemas are plain `BaseModel`, so
# `parse_obj` already ignores unknown fields in both pydantic versions — no shim, and nothing to
# assert about strictness.
GATEWAY_REQUESTS: dict[str, Any] = {
    "register_replica_request": RegisterReplicaRequest,
    "register_service_request": RegisterServiceRequest,
}


class TestRunnerResponseParsing:
    @pytest.mark.parametrize("name", sorted(RUNNER_RESPONSES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(RUNNER_RESPONSES[name], _load_input("runner", name))
        _assert_parses("runner", name, model, regen)


class TestGatewayRequestParsing:
    @pytest.mark.parametrize("name", sorted(GATEWAY_REQUESTS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = GATEWAY_REQUESTS[name].parse_obj(_load_input("gateway", name))
        _assert_parses("gateway", name, model, regen)


class TestDbBlobExtraFieldTolerance:
    """
    Every stored model must survive a row extended by a newer writer.
    """

    @pytest.mark.parametrize("name", sorted(SERIALIZED_DB_BLOBS))
    def test_unknown_field_is_dropped(self, name):
        committed = (FIXTURES_DIR / "serialization" / "db" / f"{name}.json").read_text()
        perturbed = {**json.loads(committed), "unknown_from_a_newer_writer": {"x": [1]}}
        model = type(SERIALIZED_DB_BLOBS[name]())
        parsed = parse_ignore_extra(model, perturbed)
        assert canonicalize(parsed.json()) == canonicalize(committed)


class TestRequestBodyParsing:
    @pytest.mark.parametrize("name", sorted(REQUEST_BODIES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_forbid_extra(REQUEST_BODIES[name], _load_input("api_request", name))
        _assert_parses("api_request", name, model, regen)

    @pytest.mark.parametrize("name", sorted(REQUEST_BODIES))
    def test_unknown_field_is_still_rejected(self, name):
        """
        Forbidding extra fields is the feature here: it is what makes `dstack apply` report a
        typo'd key instead of silently ignoring it. The v2 `CoreModel` forbids them by default
        with a per-call `extra="ignore"` override, so the regression to guard against is that
        override leaking onto a request path.
        """
        body = {**_load_input("api_request", name), "definitely_not_a_field": 1}
        with pytest.raises(Exception, match="(?i)extra"):
            parse_forbid_extra(REQUEST_BODIES[name], body)


class TestClientResponseParsing:
    @pytest.mark.parametrize("name", sorted(CLIENT_RESPONSES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(CLIENT_RESPONSES[name], _load_input("api_response", name))
        _assert_parses("api_response", name, model, regen)


class TestConfigParsing:
    @pytest.mark.parametrize("name", sorted(CONFIGS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_forbid_extra(CONFIGS[name], _load_yaml_input("config", name))
        _assert_parses("config", name, model, regen)


def _assert_parses(surface: str, name: str, model, regen: bool) -> None:
    kind = f"parsing/{surface}"
    assert_matches_fixture(kind, f"{name}.values", model.json(), regen=regen)
    assert_matches_fixture(kind, f"{name}.types", json.dumps(type_map(model)), regen=regen)


def _load_input(surface: str, name: str) -> Any:
    return json.loads((FIXTURES_DIR / "parsing" / surface / f"{name}.input.json").read_text())


def _load_yaml_input(surface: str, name: str) -> Any:
    return yaml.safe_load((FIXTURES_DIR / "parsing" / surface / f"{name}.input.yml").read_text())
