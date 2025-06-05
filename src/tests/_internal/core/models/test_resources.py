from typing import Optional

import pytest
from gpuhunt import AcceleratorVendor, CPUArchitecture
from pydantic import ValidationError, parse_obj_as

from dstack._internal.core.models.resources import (
    DEFAULT_CPU_COUNT,
    ComputeCapability,
    CPUSpec,
    GPUSpec,
    Memory,
    Range,
)


class TestMemory:
    def test_mb(self):
        assert parse_obj_as(Memory, "512MB") == 0.5

    def test_gb(self):
        assert parse_obj_as(Memory, "16 Gb") == 16.0

    def test_tb(self):
        assert parse_obj_as(Memory, "1 TB ") == 1024.0

    def test_float(self):
        assert parse_obj_as(Memory, 1.5) == 1.5

    def test_int(self):
        assert parse_obj_as(Memory, 1) == 1.0

    def test_invalid(self):
        with pytest.raises(ValidationError):
            parse_obj_as(Memory, "1.5xb")


class TestComputeCapability:
    def test_str(self):
        assert parse_obj_as(ComputeCapability, "3.5") == (3, 5)

    def test_float(self):
        assert parse_obj_as(ComputeCapability, 8.0) == (8, 0)

    def test_tuple(self):
        assert parse_obj_as(ComputeCapability, (7, 5)) == (7, 5)

    def test_invalid_len(self):
        with pytest.raises(ValidationError):
            parse_obj_as(ComputeCapability, "3.5.1")

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            parse_obj_as(ComputeCapability, "3.x")


class TestIntRange:
    def test_int(self):
        assert parse_obj_as(Range[int], 1).dict() == dict(min=1, max=1)

    def test_exact(self):
        assert parse_obj_as(Range[int], "1").dict() == dict(min=1, max=1)

    def test_from(self):
        assert parse_obj_as(Range[int], "1..").dict() == dict(min=1, max=None)

    def test_to(self):
        assert parse_obj_as(Range[int], "..1").dict() == dict(min=None, max=1)

    def test_invalid_range(self):
        with pytest.raises(ValidationError):
            parse_obj_as(Range[int], "..")

    def test_range_typo(self):
        with pytest.raises(ValidationError):
            parse_obj_as(Range[int], "1...3")

    def test_dict(self):
        assert parse_obj_as(Range[int], {"min": 1, "max": 3}).dict() == dict(min=1, max=3)

    def test_unordered(self):
        with pytest.raises(ValidationError):
            parse_obj_as(Range[int], "3..1")

    def test__str__(self):
        assert isinstance(str(parse_obj_as(Range[int], "1")), str)


class TestMemoryRange:
    def test_mb(self):
        assert parse_obj_as(Range[Memory], "512MB").dict() == dict(min=0.5, max=0.5)

    def test_from(self):
        assert parse_obj_as(Range[Memory], "512MB..").dict() == dict(min=0.5, max=None)

    def test_to(self):
        assert parse_obj_as(Range[Memory], "..1 TB").dict() == dict(min=None, max=1024.0)

    def test_range(self):
        assert parse_obj_as(Range[Memory], "512..1 TB").dict() == dict(min=512.0, max=1024.0)

    def test_invalid_range(self):
        with pytest.raises(ValidationError):
            parse_obj_as(Range[Memory], "...")

    def test_dict(self):
        assert parse_obj_as(Range[Memory], {"min": "512MB", "max": "1TB"}).dict() == dict(
            min=0.5, max=1024.0
        )


class TestCPU:
    def test_integer(self):
        assert parse_obj_as(CPUSpec, 1).dict() == {"arch": None, "count": {"min": 1, "max": 1}}

    @pytest.mark.parametrize(
        ["value", "expected_arch", "expected_min", "expected_max"],
        [
            ["1..2", None, 1, 2],
            ["X86", CPUArchitecture.X86, DEFAULT_CPU_COUNT.min, DEFAULT_CPU_COUNT.max],
            ["x86:2", CPUArchitecture.X86, 2, 2],
            ["2..:ARM", CPUArchitecture.ARM, 2, None],
        ],
    )
    def test_valid_string(
        self,
        value: str,
        expected_arch: Optional[CPUArchitecture],
        expected_min: Optional[int],
        expected_max: Optional[int],
    ):
        assert parse_obj_as(CPUSpec, value).dict() == {
            "arch": expected_arch,
            "count": {"min": expected_min, "max": expected_max},
        }

    @pytest.mark.parametrize(
        ["value", "error"],
        [
            ["arm:", "CPU spec contains empty token"],
            ["2:foo", "Invalid CPU architecture"],
            ["arm:x86", "CPU spec arch conflict"],
            ["2:arm:2", "CPU spec count conflict"],
        ],
    )
    def test_invalid_string(self, value: str, error: str):
        with pytest.raises(ValidationError, match=error):
            parse_obj_as(CPUSpec, value)

    def test_range_object(self):
        assert parse_obj_as(CPUSpec, Range[int](min=1, max=2)).dict() == {
            "arch": None,
            "count": {"min": 1, "max": 2},
        }

    def test_range_dict(self):
        assert parse_obj_as(CPUSpec, {"min": 1, "max": 2}).dict() == {
            "arch": None,
            "count": {"min": 1, "max": 2},
        }

    def test_valid_dict(self):
        assert parse_obj_as(CPUSpec, {"arch": "ARM", "count": {"min": 1, "max": 2}}).dict() == {
            "arch": CPUArchitecture.ARM,
            "count": {"min": 1, "max": 2},
        }

    def test_invalid_dict(self):
        with pytest.raises(ValidationError):
            parse_obj_as(CPUSpec, {"arch": "x86", "min": 1, "max": 2})


class TestGPU:
    def test_count(self):
        assert parse_obj_as(GPUSpec, "1") == parse_obj_as(GPUSpec, {"count": 1})

    @pytest.mark.parametrize(
        ["value", "expected"],
        [
            pytest.param(
                "Nvidia", {"vendor": AcceleratorVendor.NVIDIA}, id="vendor-only-mixedcase"
            ),
            pytest.param(
                "google:v3-64",
                {"vendor": AcceleratorVendor.GOOGLE, "name": ["v3-64"]},
                id="vendor-lowercase-and-name",
            ),
            pytest.param(
                "tpu:v5p-1024",
                {"vendor": AcceleratorVendor.GOOGLE, "name": ["v5p-1024"]},
                id="tpu-lowercase-and-name",
            ),
            pytest.param(
                "v5litepod-64:TPU",
                {"vendor": AcceleratorVendor.GOOGLE, "name": ["v5litepod-64"]},
                id="name-and-tpu-uppercase",
            ),
            pytest.param(
                "MI300X:AMD",
                {"vendor": AcceleratorVendor.AMD, "name": ["MI300X"]},
                id="name-and-vendor-uppercase",
            ),
        ],
    )
    def test_vendor_in_string_form(self, value, expected):
        assert parse_obj_as(GPUSpec, value) == parse_obj_as(GPUSpec, expected)

    @pytest.mark.parametrize(
        ["value", "expected"],
        [
            pytest.param(None, None, id="null"),
            pytest.param("NVIDIA", AcceleratorVendor.NVIDIA, id="uppercase"),
            pytest.param("amd", AcceleratorVendor.AMD, id="lowercase"),
            pytest.param("Google", AcceleratorVendor.GOOGLE, id="mixedcase"),
            pytest.param("tpu", AcceleratorVendor.GOOGLE, id="tpu-lowercase"),
            pytest.param("TPU", AcceleratorVendor.GOOGLE, id="tpu-uppercase"),
            pytest.param(AcceleratorVendor.GOOGLE, AcceleratorVendor.GOOGLE, id="enum-value"),
        ],
    )
    def test_vendor_in_object_form(self, value, expected):
        assert parse_obj_as(GPUSpec, {"vendor": value}) == parse_obj_as(
            GPUSpec, {"vendor": expected}
        )

    def test_name(self):
        assert parse_obj_as(GPUSpec, "A100") == parse_obj_as(GPUSpec, {"name": ["A100"]})

    def test_name_with_tpu_prefix(self):
        spec = parse_obj_as(GPUSpec, "tpu-v3-2048")
        assert spec.name == ["v3-2048"]

    def test_memory(self):
        assert parse_obj_as(GPUSpec, "16GB") == parse_obj_as(GPUSpec, {"memory": "16GB"})

    def test_names_count(self):
        assert parse_obj_as(GPUSpec, "A10,A10G:2") == parse_obj_as(
            GPUSpec, {"name": ["A10", "A10G"], "count": 2}
        )

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            parse_obj_as(GPUSpec, "A100,:2")

    def test_empty_token(self):
        with pytest.raises(ValidationError):
            parse_obj_as(GPUSpec, "A100:")

    def test_vendor_conflict(self):
        with pytest.raises(ValidationError, match=r"vendor conflict"):
            parse_obj_as(GPUSpec, "Nvidia:A100:2:AMD")

    def test_count_conflict(self):
        with pytest.raises(ValidationError, match=r"count conflict"):
            parse_obj_as(GPUSpec, "A100:2:3")

    def test_memory_range(self):
        assert parse_obj_as(GPUSpec, "16GB..32") == parse_obj_as(
            GPUSpec, {"memory": {"min": 16, "max": 32}}
        )


@pytest.mark.parametrize(
    ("r1", "r2", "intersection"),
    [
        (Range[int](min=1, max=2), Range[int](min=3, max=4), None),
        (Range[int](min=1, max=2), Range[int](min=2, max=3), Range[int](min=2, max=2)),
        (Range[int](min=1, max=2), Range[int](min=1, max=2), Range[int](min=1, max=2)),
        (Range[int](min=1, max=3), Range[int](min=2, max=4), Range[int](min=2, max=3)),
        (Range[int](min=1, max=4), Range[int](min=2, max=3), Range[int](min=2, max=3)),
        (Range[int](min=None, max=1), Range[int](min=2, max=None), None),
        (Range[int](min=None, max=1), Range[int](min=1, max=None), Range[int](min=1, max=1)),
        (Range[int](min=None, max=2), Range[int](min=1, max=None), Range[int](min=1, max=2)),
        (Range[int](min=None, max=1), Range[int](min=None, max=2), Range[int](min=None, max=1)),
        (Range[int](min=1, max=None), Range[int](min=2, max=None), Range[int](min=2, max=None)),
        (Range[int](min=1, max=None), Range[int](min=None, max=2), Range[int](min=1, max=2)),
    ],
)
def test_intersect_ranges(r1: Range[int], r2: Range[int], intersection: Range[int]) -> None:
    assert r1.intersect(r2) == intersection
    assert r2.intersect(r1) == intersection
