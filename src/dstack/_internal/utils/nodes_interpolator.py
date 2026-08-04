import re

from dstack._internal.utils.interpolator import InterpolatorError

_GROUPS_IP_REF = re.compile(r"\$\{\{\s*groups\[(\d+)\]\.nodes\[(\d+)\]\.IP_ADDRESS\s*\}\}")


def find_groups_ip_refs(s: str) -> list[tuple[int, int]]:
    return [(int(m.group(1)), int(m.group(2))) for m in _GROUPS_IP_REF.finditer(s)]


def interpolate_groups_ip_address(s: str, nodes: list[list[str]]) -> str:
    def repl(m: re.Match) -> str:
        gi, ni = int(m.group(1)), int(m.group(2))
        if gi >= len(nodes) or ni >= len(nodes[gi]):
            raise InterpolatorError(
                f"Invalid reference groups[{gi}].nodes[{ni}].IP_ADDRESS: out of range"
            )
        ip = nodes[gi][ni]
        if not ip:
            raise InterpolatorError(f"IP not available for groups[{gi}].nodes[{ni}].IP_ADDRESS")
        return ip

    return _GROUPS_IP_REF.sub(repl, s)
