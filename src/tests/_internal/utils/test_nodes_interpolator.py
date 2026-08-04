import pytest

from dstack._internal.utils.interpolator import InterpolatorError
from dstack._internal.utils.nodes_interpolator import (
    find_groups_ip_refs,
    interpolate_groups_ip_address,
)


class TestFindGroupsIpRefs:
    def test_finds_refs(self):
        s = "ray start --address=${{ groups[0].nodes[0].IP_ADDRESS }}:6379"
        assert find_groups_ip_refs(s) == [(0, 0)]

    def test_finds_multiple_refs(self):
        s = "${{ groups[0].nodes[1].IP_ADDRESS }} ${{groups[2].nodes[0].IP_ADDRESS}}"
        assert find_groups_ip_refs(s) == [(0, 1), (2, 0)]

    def test_no_refs(self):
        assert find_groups_ip_refs("echo hello") == []


class TestInterpolateGroupsIpAddress:
    def test_replaces_ip(self):
        s = "ray start --address=${{ groups[0].nodes[0].IP_ADDRESS }}:6379"
        result = interpolate_groups_ip_address(s, [["10.0.0.1", "10.0.0.2"], ["10.0.0.3"]])
        assert result == "ray start --address=10.0.0.1:6379"

    def test_replaces_nested_node(self):
        s = "${{ groups[1].nodes[0].IP_ADDRESS }}"
        result = interpolate_groups_ip_address(s, [["10.0.0.1"], ["10.0.0.2"]])
        assert result == "10.0.0.2"

    def test_raises_when_ip_missing(self):
        with pytest.raises(InterpolatorError, match="IP not available"):
            interpolate_groups_ip_address("${{ groups[0].nodes[0].IP_ADDRESS }}", [[""]])

    def test_raises_when_out_of_range(self):
        with pytest.raises(InterpolatorError, match="out of range"):
            interpolate_groups_ip_address("${{ groups[1].nodes[0].IP_ADDRESS }}", [["10.0.0.1"]])
