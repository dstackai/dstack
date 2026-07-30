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

# Parse cases are derived from the serialization surfaces rather than listed again: every model we
# write, we also read, and a model added on one side must not silently lack coverage on the other.
#
# The input for each case is the payload v1 produced, frozen on disk. Where a hand-written input
# already exists it is kept instead — those are strictly better, because they carry shapes a
# canonical dump cannot show: a row missing fields that now default, or YAML shorthand.
#
# `extra` policy follows the reader, not the model: the server forbids unknown fields in a request
# body and ignores them in a stored row.
READ_SURFACES: dict[str, str] = {
    "db": "ignore",
    "api_request": "forbid",
    "api_response": "ignore",
    "gateway": "ignore",
}


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


# Derived coverage: a serialization fixture is already a valid payload, so injecting one unknown
# key into it reproduces exactly what a reader faces when the writer is a newer version. No
# hand-written input needed, so this scales to every model on the surface for free.
#
# Only listed where *we* are the reader. `serialization/runner` is read by the Go runner and
# `serialization/proxy` by an upstream model server — we cannot assert anything about how those parse.
TOLERANT_SURFACES = ("db", "api_response", "gateway", "proxy_response")

# Same trick, opposite expectation: these are read with extra="forbid", so the injected key must
# be an error rather than be dropped.
FORBIDDING_SURFACES = ("api_request",)

_TOLERANCE_CASES = [c for c in ser._CASES if c[0] in TOLERANT_SURFACES]
_FORBID_CASES = [c for c in ser._CASES if c[0] in FORBIDDING_SURFACES]


class TestUnknownFieldTolerance:
    """Failing to read one model is a distinct bug from failing to read another, so cover all."""

    @pytest.mark.parametrize(("surface", "name"), _TOLERANCE_CASES, ids=_case_id)
    def test_unknown_field_is_dropped(self, surface, name):
        # The payload is produced from the factory rather than read from the committed fixture:
        # the fixture is already pinned by `test_serialization`, and reading it here would make
        # this test depend on that one having run first — which it has not, since `test_parsing`
        # collects earlier.
        #
        # Compare perturbed against the *same payload parsed without* the extra key rather than
        # against the payload itself. Parsing validates, and validation coerces defaults that were
        # never validated on the way out — `Volume.cost: float = 0` holds an int until something
        # parses it — so comparing to the input would fail for unrelated reasons.
        registry, dump = ser.SURFACES[surface]
        model = type(registry[name]())
        payload = json.loads(ser.serialize(surface, name))
        baseline = parse_ignore_extra(model, payload)
        perturbed = parse_ignore_extra(model, {**payload, "unknown_from_a_newer_writer": {"x": 1}})
        assert canonicalize(dump(perturbed)) == canonicalize(dump(baseline))


class TestUnknownFieldRejection:
    """
    The mirror image, and the reason the two lists are separate.

    Forbidding extra fields is what makes `dstack apply` report a typo'd key instead of ignoring
    it. The v2 `CoreModel` forbids by default with a per-call `extra="ignore"` override, so the
    regression to guard against is that override leaking onto a surface listed here.
    """

    @pytest.mark.parametrize(("surface", "name"), _FORBID_CASES, ids=_case_id)
    def test_unknown_field_is_rejected(self, surface, name):
        registry, _ = ser.SURFACES[surface]
        perturbed = {**json.loads(ser.serialize(surface, name)), "definitely_not_a_field": 1}
        with pytest.raises(Exception, match="(?i)extra"):
            parse_forbid_extra(type(registry[name]()), perturbed)


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
