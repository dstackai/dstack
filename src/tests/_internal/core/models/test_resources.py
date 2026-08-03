from typing import Optional

import pytest
from gpuhunt import AcceleratorVendor, CPUArchitecture
from pydantic import TypeAdapter, ValidationError

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
        assert TypeAdapter(Memory).validate_python("512MB") == 0.5

    def test_gb(self):
        assert TypeAdapter(Memory).validate_python("16 Gb") == 16.0

    def test_tb(self):
        assert TypeAdapter(Memory).validate_python("1 TB ") == 1024.0

    def test_float(self):
        assert TypeAdapter(Memory).validate_python(1.5) == 1.5

    def test_int(self):
        assert TypeAdapter(Memory).validate_python(1) == 1.0

    def test_invalid(self):
        with pytest.raises(ValidationError):
            TypeAdapter(Memory).validate_python("1.5xb")


class TestComputeCapability:
    def test_str(self):
        assert TypeAdapter(ComputeCapability).validate_python("3.5") == (3, 5)

    def test_float(self):
        assert TypeAdapter(ComputeCapability).validate_python(8.0) == (8, 0)

    def test_tuple(self):
        assert TypeAdapter(ComputeCapability).validate_python((7, 5)) == (7, 5)

    def test_invalid_len(self):
        with pytest.raises(ValidationError):
            TypeAdapter(ComputeCapability).validate_python("3.5.1")

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            TypeAdapter(ComputeCapability).validate_python("3.x")


class TestIntRange:
    def test_int(self):
        assert Range[int].model_validate(1).model_dump() == dict(min=1, max=1)

    def test_exact(self):
        assert Range[int].model_validate("1").model_dump() == dict(min=1, max=1)

    def test_from(self):
        assert Range[int].model_validate("1..").model_dump() == dict(min=1, max=None)

    def test_to(self):
        assert Range[int].model_validate("..1").model_dump() == dict(min=None, max=1)

    def test_invalid_range(self):
        with pytest.raises(ValidationError):
            Range[int].model_validate("..")

    def test_range_typo(self):
        with pytest.raises(ValidationError):
            Range[int].model_validate("1...3")

    def test_dict(self):
        assert Range[int].model_validate({"min": 1, "max": 3}).model_dump() == dict(min=1, max=3)

    def test_unordered(self):
        with pytest.raises(ValidationError):
            Range[int].model_validate("3..1")

    def test__str__(self):
        assert isinstance(str(Range[int].model_validate("1")), str)


class TestMemoryRange:
    def test_mb(self):
        assert Range[Memory].model_validate("512MB").model_dump() == dict(min=0.5, max=0.5)

    def test_from(self):
        assert Range[Memory].model_validate("512MB..").model_dump() == dict(min=0.5, max=None)

    def test_to(self):
        assert Range[Memory].model_validate("..1 TB").model_dump() == dict(min=None, max=1024.0)

    def test_range(self):
        assert Range[Memory].model_validate("512..1 TB").model_dump() == dict(
            min=512.0, max=1024.0
        )

    def test_invalid_range(self):
        with pytest.raises(ValidationError):
            Range[Memory].model_validate("...")

    def test_dict(self):
        assert Range[Memory].model_validate({"min": "512MB", "max": "1TB"}).model_dump() == dict(
            min=0.5, max=1024.0
        )


class TestCPU:
    def test_integer(self):
        assert CPUSpec.model_validate(1).model_dump() == {
            "arch": None,
            "count": {"min": 1, "max": 1},
        }

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
        assert CPUSpec.model_validate(value).model_dump() == {
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
            CPUSpec.model_validate(value)

    def test_range_object(self):
        assert CPUSpec.model_validate(Range[int](min=1, max=2)).model_dump() == {
            "arch": None,
            "count": {"min": 1, "max": 2},
        }

    def test_range_dict(self):
        assert CPUSpec.model_validate({"min": 1, "max": 2}).model_dump() == {
            "arch": None,
            "count": {"min": 1, "max": 2},
        }

    def test_valid_dict(self):
        assert CPUSpec.model_validate(
            {"arch": "ARM", "count": {"min": 1, "max": 2}}
        ).model_dump() == {
            "arch": CPUArchitecture.ARM,
            "count": {"min": 1, "max": 2},
        }

    def test_invalid_dict(self):
        with pytest.raises(ValidationError):
            CPUSpec.model_validate({"arch": "x86", "min": 1, "max": 2})


class TestGPU:
    def test_count(self):
        assert GPUSpec.model_validate("1") == GPUSpec.model_validate({"count": 1})

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
        assert GPUSpec.model_validate(value) == GPUSpec.model_validate(expected)

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
        assert GPUSpec.model_validate({"vendor": value}) == GPUSpec.model_validate(
            {"vendor": expected}
        )

    def test_name(self):
        assert GPUSpec.model_validate("A100") == GPUSpec.model_validate({"name": ["A100"]})

    def test_name_with_tpu_prefix(self):
        spec = GPUSpec.model_validate("tpu-v3-2048")
        assert spec.name == ["v3-2048"]

    def test_memory(self):
        assert GPUSpec.model_validate("16GB") == GPUSpec.model_validate({"memory": "16GB"})

    def test_names_count(self):
        assert GPUSpec.model_validate("A10,A10G:2") == GPUSpec.model_validate(
            {"name": ["A10", "A10G"], "count": 2}
        )

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            GPUSpec.model_validate("A100,:2")

    def test_empty_token(self):
        with pytest.raises(ValidationError):
            GPUSpec.model_validate("A100:")

    def test_vendor_conflict(self):
        with pytest.raises(ValidationError, match=r"vendor conflict"):
            GPUSpec.model_validate("Nvidia:A100:2:AMD")

    def test_count_conflict(self):
        with pytest.raises(ValidationError, match=r"count conflict"):
            GPUSpec.model_validate("A100:2:3")

    def test_memory_range(self):
        assert GPUSpec.model_validate("16GB..32") == GPUSpec.model_validate(
            {"memory": {"min": 16, "max": 32}}
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
