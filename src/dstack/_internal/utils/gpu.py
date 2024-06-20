import re


def convert_gpu_name(name: str) -> str:
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
    name = name.replace("RTX ", "RTX")
    m = re.search(r"([A|H|L|P|T|V]\d+[Ti]?)", name)
    if m is not None:
        return m.group(0)
    return name.replace(" ", "")
