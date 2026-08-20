import re
from typing import Literal

from dstack._internal.utils.interpolator import InterpolatorError, namespace_root

GroupsIpMember = Literal["nodes", "replicas"]

# Shared grammar for groups[i].(nodes|replicas)[j].IP_ADDRESS refs.
_GROUPS_IP_INNER = r"groups\[(\d+)\]\.(nodes|replicas)\[(\d+)\]\.IP_ADDRESS"
_GROUPS_IP_REF_NAME = re.compile(rf"^{_GROUPS_IP_INNER}$")
# (?<!\$) skips $${{ ... }} escapes (same rule as VariablesInterpolator).
_GROUPS_IP_REF = re.compile(rf"(?<!\$)\$\{{\{{\s*{_GROUPS_IP_INNER}\s*\}}\}}")
_NODES_IP_INNER = r"groups\[(\d+)\]\.nodes\[(\d+)\]\.IP_ADDRESS"
_NODES_IP_REF = re.compile(rf"(?<!\$)\$\{{\{{\s*{_NODES_IP_INNER}\s*\}}\}}")
_REPLICAS_IP_INNER = r"groups\[(\d+)\]\.replicas\[(\d+)\]\.IP_ADDRESS"
_REPLICAS_IP_REF = re.compile(rf"(?<!\$)\$\{{\{{\s*{_REPLICAS_IP_INNER}\s*\}}\}}")
_ANY_REF = re.compile(r"(?<!\$)\$\{\{\s*([^}]+?)\s*\}\}")


def is_valid_groups_ip_ref(name: str) -> bool:
    return _GROUPS_IP_REF_NAME.fullmatch(name.strip()) is not None


def is_groups_namespace(name: str) -> bool:
    return namespace_root(name) == "groups"


def validate_groups_refs(s: str) -> None:
    """Reject typo'd / unknown groups refs so they never reach the container."""
    for m in _ANY_REF.finditer(s):
        name = m.group(1).strip()
        if is_groups_namespace(name):
            if not is_valid_groups_ip_ref(name):
                raise InterpolatorError(f"Illegal reference name: {name}")


def contains_groups_ref(s: str) -> bool:
    for m in _ANY_REF.finditer(s):
        name = m.group(1).strip()
        if is_groups_namespace(name):
            return True
    return False


def find_groups_ip_refs(s: str) -> list[tuple[int, GroupsIpMember, int]]:
    refs: list[tuple[int, GroupsIpMember, int]] = []
    for m in _GROUPS_IP_REF.finditer(s):
        member = m.group(2)
        if member != "nodes" and member != "replicas":
            continue
        refs.append((int(m.group(1)), member, int(m.group(3))))
    return refs


def validate_groups_ref_member(s: str, expected: GroupsIpMember) -> None:
    """Reject groups refs whose member does not match the run type."""
    for group_index, member, index in find_groups_ip_refs(s):
        if member != expected:
            raise InterpolatorError(
                f"Illegal reference name: groups[{group_index}].{member}[{index}].IP_ADDRESS"
            )


def validate_groups_ref_bounds(
    s: str,
    group_sizes: list[int],
    *,
    member: GroupsIpMember = "nodes",
) -> None:
    """Reject groups[i].{member}[j] refs that exceed configured group/slot counts."""
    for group_index, ref_member, index in find_groups_ip_refs(s):
        if ref_member != member:
            continue
        if group_index >= len(group_sizes) or index >= group_sizes[group_index]:
            if (
                member == "replicas"
                and group_index < len(group_sizes)
                and group_sizes[group_index] == 0
            ):
                raise InterpolatorError(
                    f"Invalid reference groups[{group_index}].replicas[{index}].IP_ADDRESS: "
                    "this group scales to zero, so no replica is guaranteed at start"
                )
            raise InterpolatorError(
                f"Invalid reference groups[{group_index}].{member}[{index}].IP_ADDRESS: "
                "out of range"
            )


def interpolate_groups_ip_address(s: str, nodes: list[list[str]]) -> str:
    return _interpolate_groups_member_ip_address(s, nodes, "nodes", _NODES_IP_REF)


def interpolate_groups_replica_ip_address(s: str, replicas: list[list[str]]) -> str:
    return _interpolate_groups_member_ip_address(s, replicas, "replicas", _REPLICAS_IP_REF)


def _interpolate_groups_member_ip_address(
    s: str,
    view: list[list[str]],
    member: GroupsIpMember,
    pattern: re.Pattern[str],
) -> str:
    validate_groups_refs(s)
    validate_groups_ref_member(s, member)
    validate_groups_ref_bounds(s, [len(g) for g in view], member=member)

    def repl(m: re.Match) -> str:
        gi, idx = int(m.group(1)), int(m.group(2))
        ip = view[gi][idx]
        if not ip:
            raise InterpolatorError(
                f"IP not available for groups[{gi}].{member}[{idx}].IP_ADDRESS"
            )
        return ip

    return pattern.sub(repl, s)
