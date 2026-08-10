import pytest

from dstack._internal.utils.interpolator import InterpolatorError
from dstack._internal.utils.nodes_interpolator import (
    contains_groups_ref,
    find_groups_ip_refs,
    interpolate_groups_ip_address,
    validate_groups_ref_bounds,
    validate_groups_refs,
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

    def test_ignores_escaped_refs(self):
        assert find_groups_ip_refs("$${{ groups[0].nodes[0].IP_ADDRESS }}") == []


class TestValidateGroupsRefBounds:
    def test_accepts_in_range(self):
        validate_groups_ref_bounds("${{ groups[0].nodes[0].IP_ADDRESS }}", [1, 2])

    def test_rejects_group_out_of_range(self):
        with pytest.raises(InterpolatorError, match="out of range"):
            validate_groups_ref_bounds("${{ groups[2].nodes[0].IP_ADDRESS }}", [1, 2])

    def test_rejects_node_out_of_range(self):
        with pytest.raises(InterpolatorError, match="out of range"):
            validate_groups_ref_bounds("${{ groups[0].nodes[1].IP_ADDRESS }}", [1, 2])


class TestValidateGroupsRefs:
    def test_accepts_valid_ref(self):
        validate_groups_refs("ray start --address=${{ groups[0].nodes[0].IP_ADDRESS }}:6379")

    def test_rejects_typo_field(self):
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            validate_groups_refs("${{ groups[0].nodes[0].IP }}")

    def test_rejects_typo_path(self):
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            validate_groups_refs("${{ groups[0].node[0].IP_ADDRESS }}")

    def test_rejects_named_group_ref(self):
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            validate_groups_refs("${{ groups.prefill.nodes[0].IP_ADDRESS }}")

    def test_ignores_escaped_refs(self):
        validate_groups_refs("echo $${{ groups[0].bad }}")


class TestContainsGroupsRef:
    def test_detects_valid_and_invalid_refs(self):
        assert contains_groups_ref("http://${{ groups[1].nodes[0].IP_ADDRESS }}")
        assert contains_groups_ref("${{ groups[0].nodes[0].IP }}")
        assert not contains_groups_ref("${{ secrets.token }}")
        assert not contains_groups_ref("${{ groups_config.x }}")

    def test_ignores_escaped_refs(self):
        assert not contains_groups_ref("echo $${{ groups[0].nodes[0].IP_ADDRESS }}")


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

    def test_raises_on_invalid_ref(self):
        with pytest.raises(InterpolatorError, match="Illegal reference name"):
            interpolate_groups_ip_address("${{ groups[0].nodes[0].IP }}", [["10.0.0.1"]])
