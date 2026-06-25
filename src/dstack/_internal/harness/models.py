import argparse
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from dstack._internal.core.errors import CLIError


def default_endpoint_name(model: str) -> str:
    """Derive a stable run name from a model id (e.g. org/model -> model, normalized)."""
    base = model.rsplit("/", 1)[-1]
    name = base.lower().replace(".", "-")
    name = re.sub(r"[^a-z0-9-]+", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    if not name:
        raise CLIError(f"Cannot derive an endpoint name from model [code]{model}[/]")
    return name


@dataclass
class EndpointCreateParams:
    model: str
    name: Optional[str] = None
    gpu: Optional[Any] = None
    cpu: Optional[Any] = None
    memory: Optional[Any] = None
    disk: Optional[Any] = None
    backends: List[str] = field(default_factory=list)
    regions: List[str] = field(default_factory=list)
    instance_types: List[str] = field(default_factory=list)
    fleets: List[str] = field(default_factory=list)
    max_price: Optional[float] = None
    max_duration: Optional[int] = None
    spot_policy: Optional[str] = None
    env_vars: List[str] = field(default_factory=list)

    @classmethod
    def from_namespace(cls, args: argparse.Namespace, model: str) -> "EndpointCreateParams":
        spot_policy = getattr(args, "spot_policy", None)
        return cls(
            model=model,
            name=getattr(args, "run_name", None) or default_endpoint_name(model),
            gpu=getattr(args, "gpu_spec", None),
            cpu=getattr(args, "cpu_spec", None),
            memory=getattr(args, "memory_spec", None),
            disk=getattr(args, "disk_spec", None),
            backends=getattr(args, "backends", None) or [],
            regions=getattr(args, "regions", None) or [],
            instance_types=getattr(args, "instance_types", None) or [],
            fleets=getattr(args, "fleets", None) or [],
            max_price=getattr(args, "max_price", None),
            max_duration=getattr(args, "max_duration", None),
            spot_policy=spot_policy.value if spot_policy is not None else None,
            env_vars=[item.key for item in getattr(args, "env_vars", [])],
        )

    def cli_options(self) -> Dict[str, Any]:
        options = asdict(self)
        return {key: value for key, value in options.items() if value not in (None, [], {})}
