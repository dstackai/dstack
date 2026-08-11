import re

import gpuhunt


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
    name = re.sub(r"(?i) ?SUPER", "SUPER", name)
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


def convert_intel_accelerator_name(name: str) -> str:
    """Convert name from hl-smi to market name"""
    for model_name, market_name in _INTEL_GAUDI_MODELS.items():
        if name.startswith(model_name):
            return market_name
    return name


_AMD_INSTINCT_MARKET_NAME_REGEX = re.compile(
    r"^(?:AMD )?(?:Instinct )?(?P<name>MI\d{1,3}[A-Z]?(?:-\w+)?)(?:\s|$)", flags=re.ASCII | re.I
)

_INTEL_GAUDI_MODELS = {
    "HL-205": "Gaudi",
    "HL-225": "Gaudi2",
    "HL-325": "Gaudi3",  # OAM
    "HL-338": "Gaudi3",  # PCIe
}


def detect_gpu_vendors_by_gpu_name(name: str) -> set[gpuhunt.AcceleratorVendor]:
    vendors: set[gpuhunt.AcceleratorVendor] = set()
    name = name.lower()
    if name in _KNOWN_NVIDIA_GPUS:
        vendors.add(gpuhunt.AcceleratorVendor.NVIDIA)
    if name in _KNOWN_AMD_GPUS:
        vendors.add(gpuhunt.AcceleratorVendor.AMD)
    if name in _KNOWN_INTEL_ACCELERATORS:
        vendors.add(gpuhunt.AcceleratorVendor.INTEL)
    if name in _KNOWN_TENSTORRENT_ACCELERATORS:
        vendors.add(gpuhunt.AcceleratorVendor.TENSTORRENT)
    maybe_tpu_version, _, maybe_tpu_cores = name.partition("-")
    if maybe_tpu_cores.isdigit() and maybe_tpu_version in _KNOWN_TPU_VERSIONS:
        vendors.add(gpuhunt.AcceleratorVendor.GOOGLE)
    return vendors


_KNOWN_NVIDIA_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_NVIDIA_GPUS}
_KNOWN_AMD_GPUS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_AMD_GPUS}
_KNOWN_INTEL_ACCELERATORS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_INTEL_ACCELERATORS}
_KNOWN_TENSTORRENT_ACCELERATORS = {
    gpu.name.lower() for gpu in gpuhunt.KNOWN_TENSTORRENT_ACCELERATORS
}
_KNOWN_TPU_VERSIONS = {gpu.name.lower() for gpu in gpuhunt.KNOWN_TPUS}
