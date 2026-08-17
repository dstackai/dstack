import re

from dstack._internal.utils.interpolator import InterpolatorError, namespace_root

# Shared grammar for groups[i].nodes[j].IP_ADDRESS refs.
_GROUPS_IP_INNER = r"groups\[(\d+)\]\.nodes\[(\d+)\]\.IP_ADDRESS"
_GROUPS_IP_REF_NAME = re.compile(rf"^{_GROUPS_IP_INNER}$")
# (?<!\$) skips $${{ ... }} escapes (same rule as VariablesInterpolator).
_GROUPS_IP_REF = re.compile(rf"(?<!\$)\$\{{\{{\s*{_GROUPS_IP_INNER}\s*\}}\}}")
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


def find_groups_ip_refs(s: str) -> list[tuple[int, int]]:
    return [(int(m.group(1)), int(m.group(2))) for m in _GROUPS_IP_REF.finditer(s)]


def validate_groups_ref_bounds(s: str, group_sizes: list[int]) -> None:
    """Reject groups[i].nodes[j] refs that exceed configured group/node counts."""
    for group_index, node_index in find_groups_ip_refs(s):
        if group_index >= len(group_sizes) or node_index >= group_sizes[group_index]:
            raise InterpolatorError(
                f"Invalid reference groups[{group_index}].nodes[{node_index}].IP_ADDRESS: "
                "out of range"
            )


def interpolate_groups_ip_address(s: str, nodes: list[list[str]]) -> str:
    validate_groups_refs(s)
    validate_groups_ref_bounds(s, [len(g) for g in nodes])

    def repl(m: re.Match) -> str:
        gi, ni = int(m.group(1)), int(m.group(2))
        ip = nodes[gi][ni]
        if not ip:
            raise InterpolatorError(f"IP not available for groups[{gi}].nodes[{ni}].IP_ADDRESS")
        return ip

    return _GROUPS_IP_REF.sub(repl, s)
