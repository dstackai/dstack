"""
Focused parity tests for Pydantic mechanisms that broad boundary fixtures only exercise
incidentally.

Unlike the wire fixtures, these cases are intentionally small: when a validator or generic
specialization changes during the v2 migration, the failing case should name the mechanism that
drifted.
"""

import json
from typing import Any, Callable

import pytest
from pydantic import ValidationError, parse_obj_as

from dstack._internal.core.models.common import Duration
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.resources import (
    ComputeCapability,
    CPUSpec,
    DiskSpec,
    GPUSpec,
    Memory,
    Range,
)
from dstack._internal.core.models.volumes import VolumeSpec
from dstack.plugins.builtin.rest_plugin._models import (
    FleetSpecRequest,
    FleetSpecResponse,
    GatewaySpecRequest,
    GatewaySpecResponse,
    RunSpecRequest,
    RunSpecResponse,
    VolumeSpecRequest,
    VolumeSpecResponse,
)
from tests._internal.pydantic_compat import factories
from tests._internal.pydantic_compat.compare import canonicalize, class_name, type_map


def _volume_spec() -> VolumeSpec:
    return VolumeSpec(configuration=factories.volume_configuration())


def _gateway_spec() -> GatewaySpec:
    return GatewaySpec(configuration=factories.gateway_configuration())


_REST_GENERIC_CASES = [
    pytest.param(
        RunSpecRequest,
        RunSpecResponse,
        factories.run_spec,
        "RunSpec",
        id="run",
    ),
    pytest.param(
        FleetSpecRequest,
        FleetSpecResponse,
        factories.fleet_spec,
        "FleetSpec",
        id="fleet",
    ),
    pytest.param(
        VolumeSpecRequest,
        VolumeSpecResponse,
        _volume_spec,
        "VolumeSpec",
        id="volume",
    ),
    pytest.param(
        GatewaySpecRequest,
        GatewaySpecResponse,
        _gateway_spec,
        "GatewaySpec",
        id="gateway",
    ),
]


class TestRESTPluginGenericModels:
    @pytest.mark.parametrize(
        ("request_model", "response_model", "spec_factory", "expected_spec_type"),
        _REST_GENERIC_CASES,
    )
    def test_specialization_preserves_spec_type_and_production_request_body(
        self,
        request_model: Any,
        response_model: Any,
        spec_factory: Callable[[], Any],
        expected_spec_type: str,
    ):
        """
        Pydantic v1 represents these specializations as typing aliases and adds
        `__orig_class__` after construction. Production sends `.dict()` to requests, relying on
        the request model's override to remove that non-JSON value.
        """
        spec = spec_factory()
        request = request_model(user="alice", project="main", spec=spec)

        assert class_name(request.spec) == expected_spec_type
        body = request.dict()
        assert "__orig_class__" not in body

        # Match the exact production handoff: requests receives a plain, stdlib-JSON-safe dict.
        encoded_body = json.dumps(body)
        assert canonicalize(json.dumps(body["spec"])) == canonicalize(spec.json())

        # The generic must also choose the same type when its value arrives as an untyped payload.
        reparsed_request = request_model(**json.loads(encoded_body))
        assert class_name(reparsed_request.spec) == expected_spec_type

        # This is the production response path in CustomApplyPolicy._on_apply.
        response = response_model(spec=body["spec"], error=None)
        assert class_name(response.spec) == expected_spec_type
        assert response.error is None


_RANGE_CASES = [
    pytest.param(Range[int], 2, {"min": 2, "max": 2}, int, id="int-scalar"),
    pytest.param(Range[int], "2..8", {"min": 2, "max": 8}, int, id="int-closed"),
    pytest.param(Range[int], "2..", {"min": 2, "max": None}, int, id="int-open-max"),
    pytest.param(
        Range[int],
        {"min": None, "max": 8},
        {"min": None, "max": 8},
        int,
        id="int-mapping",
    ),
    pytest.param(
        Range[Memory],
        "512MB",
        {"min": 0.5, "max": 0.5},
        Memory,
        id="memory-scalar",
    ),
    pytest.param(
        Range[Memory],
        "512MB..1TB",
        {"min": 0.5, "max": 1024.0},
        Memory,
        id="memory-closed",
    ),
    pytest.param(
        Range[Memory],
        {"min": "16GB", "max": None},
        {"min": 16.0, "max": None},
        Memory,
        id="memory-mapping",
    ),
]


class TestRangeGenericModel:
    @pytest.mark.parametrize(("range_type", "raw", "expected", "bound_type"), _RANGE_CASES)
    def test_specialization_preserves_bound_types_and_json(
        self,
        range_type: Any,
        raw: Any,
        expected: dict[str, Any],
        bound_type: type,
    ):
        value = parse_obj_as(range_type, raw)

        assert type(value) is range_type
        assert value.dict() == expected
        for bound in (value.min, value.max):
            if bound is not None:
                assert type(bound) is bound_type
        assert canonicalize(value.json()) == canonicalize(json.dumps(expected))

    @pytest.mark.parametrize("raw", ["..", "8..2", "1...3"])
    def test_invalid_int_ranges_stay_rejected(self, raw: str):
        with pytest.raises(ValidationError):
            parse_obj_as(Range[int], raw)

    @pytest.mark.parametrize("raw", ["...", "2TB..1TB"])
    def test_invalid_memory_ranges_stay_rejected(self, raw: str):
        with pytest.raises(ValidationError):
            parse_obj_as(Range[Memory], raw)


_SCALAR_CASES = [
    pytest.param(Duration, 90, 90, Duration, 90, id="duration-int"),
    pytest.param(Duration, 1.9, 1, Duration, 1, id="duration-float-truncates"),
    pytest.param(Duration, "90", 90, Duration, 90, id="duration-numeric-string"),
    pytest.param(Duration, "2 h", 7200, Duration, 7200, id="duration-unit"),
    pytest.param(Duration, "1w", 604800, Duration, 604800, id="duration-week"),
    pytest.param(Memory, 1, 1.0, Memory, 1.0, id="memory-int"),
    pytest.param(Memory, 1.5, 1.5, Memory, 1.5, id="memory-float"),
    pytest.param(Memory, "512MB", 0.5, Memory, 0.5, id="memory-mb"),
    pytest.param(Memory, "16 Gb", 16.0, Memory, 16.0, id="memory-gb"),
    pytest.param(Memory, "1 TB ", 1024.0, Memory, 1024.0, id="memory-tb"),
    pytest.param(
        ComputeCapability,
        "3.5",
        (3, 5),
        tuple,
        [3, 5],
        id="compute-capability-string",
    ),
    pytest.param(
        ComputeCapability,
        8.0,
        (8, 0),
        tuple,
        [8, 0],
        id="compute-capability-float",
    ),
    pytest.param(
        ComputeCapability,
        [7, 5],
        (7, 5),
        tuple,
        [7, 5],
        id="compute-capability-list",
    ),
    pytest.param(
        ComputeCapability,
        (9, 0),
        (9, 0),
        tuple,
        [9, 0],
        id="compute-capability-tuple",
    ),
]


class TestCustomScalarTypes:
    @pytest.mark.parametrize(
        ("scalar_type", "raw", "expected", "expected_type", "expected_json"),
        _SCALAR_CASES,
    )
    def test_parsed_value_type_and_json_stay_stable(
        self,
        scalar_type: Any,
        raw: Any,
        expected: Any,
        expected_type: type,
        expected_json: Any,
    ):
        value = parse_obj_as(scalar_type, raw)

        assert value == expected
        assert type(value) is expected_type
        assert canonicalize(json.dumps(value)) == canonicalize(json.dumps(expected_json))

    @pytest.mark.parametrize(
        ("scalar_type", "raw"),
        [
            pytest.param(Duration, "5 years", id="duration-bad-unit"),
            pytest.param(Duration, {}, id="duration-bad-type"),
            pytest.param(Memory, "1.5xb", id="memory-bad-unit"),
            pytest.param(Memory, {}, id="memory-bad-type"),
            pytest.param(ComputeCapability, "3.5.1", id="compute-capability-length"),
            pytest.param(ComputeCapability, "3.x", id="compute-capability-component"),
        ],
    )
    def test_invalid_values_stay_rejected(self, scalar_type: Any, raw: Any):
        with pytest.raises(ValidationError):
            parse_obj_as(scalar_type, raw)


_CUSTOM_MODEL_CASES = [
    pytest.param(
        CPUSpec,
        1,
        {"arch": None, "count": {"min": 1, "max": 1}},
        {"/": "CPUSpec", "/count": "Range[int]"},
        id="cpu-scalar",
    ),
    pytest.param(
        CPUSpec,
        "x86:2",
        {"arch": "x86", "count": {"min": 2, "max": 2}},
        {"/": "CPUSpec", "/arch": "CPUArchitecture", "/count": "Range[int]"},
        id="cpu-architecture-and-count",
    ),
    pytest.param(
        CPUSpec,
        "2..:ARM",
        {"arch": "arm", "count": {"min": 2, "max": None}},
        {"/": "CPUSpec", "/arch": "CPUArchitecture", "/count": "Range[int]"},
        id="cpu-open-range-and-architecture",
    ),
    pytest.param(
        CPUSpec,
        {"min": 1, "max": 2},
        {"arch": None, "count": {"min": 1, "max": 2}},
        {"/": "CPUSpec", "/count": "Range[int]"},
        id="cpu-legacy-range-mapping",
    ),
    pytest.param(
        GPUSpec,
        "1",
        {
            "vendor": None,
            "name": None,
            "count": {"min": 1, "max": 1},
            "memory": None,
            "total_memory": None,
            "compute_capability": None,
        },
        {"/": "GPUSpec", "/count": "Range[int]"},
        id="gpu-count",
    ),
    pytest.param(
        GPUSpec,
        "A10,A10G:2",
        {
            "vendor": None,
            "name": ["A10", "A10G"],
            "count": {"min": 2, "max": 2},
            "memory": None,
            "total_memory": None,
            "compute_capability": None,
        },
        {"/": "GPUSpec", "/count": "Range[int]"},
        id="gpu-names-and-count",
    ),
    pytest.param(
        GPUSpec,
        "tpu:v5p-8:2:16GB..32GB",
        {
            "vendor": "google",
            "name": ["v5p-8"],
            "count": {"min": 2, "max": 2},
            "memory": {"min": 16.0, "max": 32.0},
            "total_memory": None,
            "compute_capability": None,
        },
        {
            "/": "GPUSpec",
            "/vendor": "AcceleratorVendor",
            "/count": "Range[int]",
            "/memory": "Range[Memory]",
            "/memory/min": "Memory",
            "/memory/max": "Memory",
        },
        id="gpu-tpu-alias-and-memory-range",
    ),
    pytest.param(
        GPUSpec,
        "tt:n300:2",
        {
            "vendor": "tenstorrent",
            "name": ["n300"],
            "count": {"min": 2, "max": 2},
            "memory": None,
            "total_memory": None,
            "compute_capability": None,
        },
        {
            "/": "GPUSpec",
            "/vendor": "AcceleratorVendor",
            "/count": "Range[int]",
        },
        id="gpu-tenstorrent-alias",
    ),
    pytest.param(
        DiskSpec,
        "100GB..",
        {"size": {"min": 100.0, "max": None}},
        {"/": "DiskSpec", "/size": "Range[Memory]", "/size/min": "Memory"},
        id="disk-scalar",
    ),
    pytest.param(
        DiskSpec,
        {"size": {"min": "1TB", "max": "2TB"}},
        {"size": {"min": 1024.0, "max": 2048.0}},
        {
            "/": "DiskSpec",
            "/size": "Range[Memory]",
            "/size/min": "Memory",
            "/size/max": "Memory",
        },
        id="disk-mapping",
    ),
]


class TestCustomModelTypes:
    @pytest.mark.parametrize(
        ("model_type", "raw", "expected_json", "expected_types"),
        _CUSTOM_MODEL_CASES,
    )
    def test_custom_parser_preserves_values_types_and_json(
        self,
        model_type: Any,
        raw: Any,
        expected_json: dict[str, Any],
        expected_types: dict[str, str],
    ):
        value = parse_obj_as(model_type, raw)

        assert canonicalize(value.json()) == canonicalize(json.dumps(expected_json))
        assert type_map(value) == expected_types

    @pytest.mark.parametrize(
        ("model_type", "raw"),
        [
            pytest.param(CPUSpec, "arm:", id="cpu-empty-token"),
            pytest.param(CPUSpec, "2:arm:2", id="cpu-count-conflict"),
            pytest.param(GPUSpec, "A100:", id="gpu-empty-token"),
            pytest.param(GPUSpec, "Nvidia:A100:2:AMD", id="gpu-vendor-conflict"),
            pytest.param(DiskSpec, "...", id="disk-invalid-range"),
        ],
    )
    def test_invalid_custom_model_values_stay_rejected(self, model_type: Any, raw: Any):
        with pytest.raises(ValidationError):
            parse_obj_as(model_type, raw)
