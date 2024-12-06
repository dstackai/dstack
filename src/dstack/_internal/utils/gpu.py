import re


def convert_nvidia_gpu_name(name: str) -> str:
    """Convert gpu_name from nvidia-smi to short version"""
    # https://github.com/NVIDIA/open-gpu-kernel-modules/
    name = name.replace("NVIDIA ", "")
    name = name.replace("Tesla ", "")
    name = name.replace("Quadro ", "")
    name = name.replace("GeForce ", "")

    if "GH200" in name:
        return "GH200"

    if "RTX A" in name:
        name = name.replace("RTX A", "A")
        m = re.search(r"(A\d+)", name)
        if m is not None:
            return m.group(0)
        return name.replace(" ", "")

    name = name.replace(" Ti", "Ti")
    name = name.replace(" NVL", "NVL")
    name = name.replace(" Ada Generation", "Ada")
    name = name.replace("RTX ", "RTX")
    m = re.search(r"([AHLPTV]\d+\w*)", name)
    if m is not None:
        return m.group(0)
    return name.replace(" ", "")


def convert_amd_gpu_name(name: str) -> str:
    """Convert asic.market_name from amd-smi to short version"""
    if match := _AMD_INSTINCT_MARKET_NAME_REGEX.search(name):
        name = match.group("name")
    # https://github.com/ROCm/amdsmi/blob/52b3947/src/amd_smi/amd_smi_utils.cc#L558-L593
    if name == "MI300X-O":
        return "MI300X"
    return name


_AMD_INSTINCT_MARKET_NAME_REGEX = re.compile(
    r"^(?:AMD )?(?:Instinct )?(?P<name>MI\d{1,3}[A-Z]?(?:-\w+)?)(?:\s|$)", flags=re.ASCII | re.I
)
