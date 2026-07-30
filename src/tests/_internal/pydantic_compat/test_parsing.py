"""
Parse equality across every boundary that reads somebody else's payload.

Each case is a frozen input plus two expectations: the values parsing produced, and the concrete
classes it chose. Both are needed — `Duration(7200)` and `7200` are the same JSON, so the value
fixture alone cannot show that a custom type survived.

Inputs are deliberately NOT canonical dumps. Feeding a model its own output back makes the
expected values identical to the input and the test proves nothing; every input here differs from
its output in some way a real writer could produce — an unknown field from a newer version, an
absent field that now defaults, or a sugared value.

Inputs are hand-written and must never be regenerated. `--regen-fixtures` rewrites
`*.values.json` and `*.types.json` only.

Registries and test classes below follow the same surface order as `test_serialization.py`:
db, api_request, api_response, config, runner, gateway, proxy.
"""

import json
from typing import Any

import pytest
import yaml

from dstack._internal.core.models.configurations import DstackConfiguration
from dstack._internal.core.models.profiles import ProfilesConfig
from dstack._internal.proxy.gateway.schemas.registry import (
    RegisterEntrypointRequest,
    RegisterReplicaRequest,
    RegisterServiceRequest,
)
from dstack._internal.proxy.gateway.schemas.stats import ServiceStats
from dstack._internal.proxy.lib.schemas.model_proxy import (
    ChatCompletionsChunk,
    ChatCompletionsRequest,
    ChatCompletionsResponse,
)
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    InstanceHealthResponse,
    JobInfoResponse,
    MetricsResponse,
    TaskInfoResponse,
)
from tests._internal.pydantic_compat import test_serialization as ser
from tests._internal.pydantic_compat.compare import (
    FIXTURES_DIR,
    assert_matches_fixture,
    canonicalize,
    type_map,
)
from tests._internal.pydantic_compat.compat import parse_forbid_extra, parse_ignore_extra

# The model *list* for each surface is taken from the serialization side rather than repeated here,
# so a model added on one side cannot silently lack coverage on the other. That is the only thing
# borrowed — every payload below is a hand-written input, because a canonical dump can never carry
# the shapes that stress a parser: fields absent as an older writer left them, values in the
# shorthand a user or CLI actually sends.
#
# `extra` policy follows the reader, not the model: the server forbids unknown fields in a request
# body and ignores them in a stored row, and the same model can appear on both sides.


def _derived_registry(surface: str) -> dict[str, Any]:
    registry, _ = ser.SURFACES[surface]
    return {name: type(factory()) for name, factory in registry.items()}


DB_BLOBS = _derived_registry("db")
API_REQUESTS = _derived_registry("api_request")
API_RESPONSES = _derived_registry("api_response")

# Parsed from user-authored YAML with extra="forbid". The only surface whose inputs are `.yml`,
# because the sugar pinned here is a YAML phenomenon: `python: 3.10` is a float that survives only
# via number->str coercion, and `16GB..` / `2..8` / an env list are shorthands people type by hand.
# `DstackConfiguration` dispatches every `.dstack.yml` type through its `__root__` union, so one
# entry point covers task, service, dev-environment, fleet, volume, and gateway.
CONFIGS: dict[str, Any] = {
    "dev_environment": DstackConfiguration,
    "fleet": DstackConfiguration,
    "profiles": ProfilesConfig,
    "service": DstackConfiguration,
    "task": DstackConfiguration,
    "volume": DstackConfiguration,
}

# Responses the server reads back from the runner (shim), permissively: a newer runner may add
# fields, and the server has no say over which runner version an instance is running.
RUNNER_RESPONSES: dict[str, Any] = {
    "healthcheck_response": HealthcheckResponse,
    "instance_health_response": InstanceHealthResponse,
    "job_info_response": JobInfoResponse,
    "metrics_response": MetricsResponse,
    "task_info_response": TaskInfoResponse,
}

# Request payloads the gateway parses from the server. These schemas are plain `BaseModel`, so
# `parse_obj` already ignores unknown fields in both pydantic versions — no shim needed, and
# nothing to assert about strictness.
GATEWAY_PAYLOADS: dict[str, Any] = {
    "register_entrypoint_request": RegisterEntrypointRequest,
    "register_replica_request": RegisterReplicaRequest,
    "register_service_request": RegisterServiceRequest,
    "service_stats": ServiceStats,
}

# The model proxy. The request comes from a caller and the response from an upstream model server,
# so both are somebody else's payload and both are read permissively. `stop` and `tool_choice` are
# two of the unions with no common Literal to discriminate on, which makes them the clearest
# smart-union cases in the codebase.
PROXY_PAYLOADS: dict[str, Any] = {
    "chat_completions_chunk": ChatCompletionsChunk,
    "chat_completions_request": ChatCompletionsRequest,
    "chat_completions_response": ChatCompletionsResponse,
}


def _case_id(value: Any) -> str:
    return str(value)


class TestDbBlobParsing:
    @pytest.mark.parametrize("name", sorted(DB_BLOBS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(DB_BLOBS[name], _load_input("db", name))
        _assert_parses("db", name, model, regen)


# Every case above earns a second assertion: inject an unknown key into the same input and check the
# reader's `extra` policy holds. That covers what happens when the writer is a newer version.
#
# Only the surfaces we read are listed. Runner request bodies are read by the Go runner and proxy
# requests by an upstream model server, so there is nothing here we could assert about how they
# parse — they are absent rather than passing vacuously.
_REGISTRIES = {
    "db": DB_BLOBS,
    "api_request": API_REQUESTS,
    "api_response": API_RESPONSES,
    "gateway": GATEWAY_PAYLOADS,
}

# Readers that ignore unknown fields, versus the one that must reject them.
_TOLERANCE_CASES = [
    (surface, name)
    for surface in ("db", "api_response", "gateway")
    for name in sorted(_REGISTRIES[surface])
]
_FORBID_CASES = [("api_request", name) for name in sorted(API_REQUESTS)]


class TestUnknownFieldTolerance:
    """Failing to read one model is a distinct bug from failing to read another, so cover all."""

    @pytest.mark.parametrize(("surface", "name"), _TOLERANCE_CASES, ids=_case_id)
    def test_unknown_field_is_dropped(self, surface, name):
        # Compare against the *same input parsed without* the extra key, not against the input
        # itself: parsing fills defaults, so the two are not expected to match.
        model = _REGISTRIES[surface][name]
        payload = _load_input(surface, name)
        baseline = parse_ignore_extra(model, payload)
        perturbed = parse_ignore_extra(model, {**payload, "unknown_from_a_newer_writer": {"x": 1}})
        assert canonicalize(perturbed.json()) == canonicalize(baseline.json())


class TestUnknownFieldRejection:
    """
    The mirror image, and the reason the two lists are separate.

    Forbidding extra fields is what makes `dstack apply` report a typo'd key instead of ignoring
    it. The v2 `CoreModel` forbids by default with a per-call `extra="ignore"` override, so the
    regression to guard against is that override leaking onto a surface listed here.
    """

    @pytest.mark.parametrize(("surface", "name"), _FORBID_CASES, ids=_case_id)
    def test_unknown_field_is_rejected(self, surface, name):
        perturbed = {**_load_input(surface, name), "definitely_not_a_field": 1}
        with pytest.raises(Exception, match="(?i)extra"):
            parse_forbid_extra(_REGISTRIES[surface][name], perturbed)


class TestApiRequestParsing:
    @pytest.mark.parametrize("name", sorted(API_REQUESTS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_forbid_extra(API_REQUESTS[name], _load_input("api_request", name))
        _assert_parses("api_request", name, model, regen)

    @pytest.mark.parametrize("name", sorted(API_REQUESTS))
    def test_unknown_field_is_still_rejected(self, name):
        """
        Forbidding extra fields is the feature here: it is what makes `dstack apply` report a
        typo'd key instead of silently ignoring it. The v2 `CoreModel` forbids them by default
        with a per-call `extra="ignore"` override, so the regression to guard against is that
        override leaking onto a request path.
        """
        body = {**_load_input("api_request", name), "definitely_not_a_field": 1}
        with pytest.raises(Exception, match="(?i)extra"):
            parse_forbid_extra(API_REQUESTS[name], body)


class TestApiResponseParsing:
    @pytest.mark.parametrize("name", sorted(API_RESPONSES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(API_RESPONSES[name], _load_input("api_response", name))
        _assert_parses("api_response", name, model, regen)


class TestConfigParsing:
    @pytest.mark.parametrize("name", sorted(CONFIGS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_forbid_extra(CONFIGS[name], _load_yaml_input("config", name))
        _assert_parses("config", name, model, regen)


class TestRunnerResponseParsing:
    @pytest.mark.parametrize("name", sorted(RUNNER_RESPONSES))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(RUNNER_RESPONSES[name], _load_input("runner", name))
        _assert_parses("runner", name, model, regen)


class TestGatewayRequestParsing:
    @pytest.mark.parametrize("name", sorted(GATEWAY_PAYLOADS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(GATEWAY_PAYLOADS[name], _load_input("gateway", name))
        _assert_parses("gateway", name, model, regen)


class TestProxyPayloadParsing:
    @pytest.mark.parametrize("name", sorted(PROXY_PAYLOADS))
    def test_parses_to_expected_values_and_types(self, name, regen):
        model = parse_ignore_extra(PROXY_PAYLOADS[name], _load_input("proxy", name))
        _assert_parses("proxy", name, model, regen)


def _assert_parses(surface: str, name: str, model, regen: bool) -> None:
    kind = f"parsing/{surface}"
    assert_matches_fixture(kind, f"{name}.values", model.json(), regen=regen)
    assert_matches_fixture(kind, f"{name}.types", json.dumps(type_map(model)), regen=regen)


def _load_input(surface: str, name: str) -> Any:
    return json.loads((FIXTURES_DIR / "parsing" / surface / f"{name}.input.json").read_text())


def _load_yaml_input(surface: str, name: str) -> Any:
    return yaml.safe_load((FIXTURES_DIR / "parsing" / surface / f"{name}.input.yml").read_text())
