from typing import Any, Optional

import pytest
from pydantic import TypeAdapter, ValidationError

from dstack._internal.core.models.duration import (
    Duration,
    OptionalIdleDuration,
    OptionalOffableDuration,
)


class TestDuration:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param(90, 90, id="int"),
            pytest.param("90", 90, id="numeric-string"),
            pytest.param(1.9, 1, id="float-truncates"),
            pytest.param("30s", 30, id="seconds"),
            pytest.param("5m", 300, id="minutes"),
            pytest.param("2h", 7200, id="hours"),
            pytest.param("2 h", 7200, id="space-before-unit"),
            pytest.param("1d", 86400, id="days"),
            pytest.param("1w", 604800, id="weeks"),
        ],
    )
    def test_parses_seconds_and_shorthands(self, raw: Any, expected: int):
        value = TypeAdapter(Duration).validate_python(raw)

        assert value == expected
        assert isinstance(value, Duration)

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("bogus", id="not-a-duration"),
            pytest.param("2y", id="unsupported-unit"),
            pytest.param("h2", id="unit-before-amount"),
            pytest.param("", id="empty"),
        ],
    )
    def test_rejects_unparsable(self, raw: str):
        with pytest.raises(ValidationError):
            TypeAdapter(Duration).validate_python(raw)

    def test_serializes_as_seconds(self):
        adapter = TypeAdapter(Duration)

        assert adapter.dump_python(Duration.parse("2h")) == 7200
        assert adapter.dump_json(Duration.parse("2h")) == b"7200"


class TestOptionalOffableDuration:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("2h", 7200, id="shorthand"),
            pytest.param(7200, 7200, id="seconds"),
            pytest.param("off", "off", id="off-string"),
            pytest.param(False, "off", id="false-means-off"),
            pytest.param(True, None, id="true-means-default"),
            pytest.param(None, None, id="unspecified"),
        ],
    )
    def test_normalizes(self, raw: Any, expected: Any):
        assert TypeAdapter(OptionalOffableDuration).validate_python(raw) == expected

    @pytest.mark.parametrize("raw", [-1, -300, "-1"])
    def test_rejects_negative(self, raw: Any):
        """Unlike `OptionalIdleDuration`, there is no negative sentinel here."""
        with pytest.raises(ValidationError):
            TypeAdapter(OptionalOffableDuration).validate_python(raw)


class TestOptionalIdleDuration:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            pytest.param("5m", 300, id="shorthand"),
            pytest.param(300, 300, id="seconds"),
            pytest.param("off", -1, id="off-string"),
            pytest.param(False, -1, id="false-means-off"),
            pytest.param(True, None, id="true-means-default"),
            pytest.param(None, None, id="unspecified"),
        ],
    )
    def test_normalizes(self, raw: Any, expected: Optional[int]):
        assert TypeAdapter(OptionalIdleDuration).validate_python(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param(-1, id="minus-one"),
            pytest.param(-300, id="other-negative"),
            pytest.param("-1", id="minus-one-string"),
        ],
    )
    def test_accepts_negative_for_backward_compatibility(self, raw: Any):
        """
        `-1` is how older clients and existing stored rows spell "off", so negatives have to keep
        parsing rather than being rejected the way `OptionalOffableDuration` rejects them.
        """
        assert TypeAdapter(OptionalIdleDuration).validate_python(raw) < 0
