import pytest
from pydantic import ValidationError, parse_obj_as

from dstack._internal.core.models.resources import ComputeCapability, Memory, Range


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
