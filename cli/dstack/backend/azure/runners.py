from typing import List, Optional, Tuple

from azure.mgmt.compute import ComputeManagementClient

from dstack.core.instance import InstanceType
from dstack.core.job import Requirements
from dstack.core.runners import Gpu, Resources


def _key_for_instance(i1: InstanceType) -> Tuple:
    return (
        sum(map(lambda g: g.memory_mib, i1.resources.gpus or [])),
        i1.resources.cpus,
        i1.resources.memory_mib,
    )


def _get_instance_types(client: ComputeManagementClient, location: str) -> List[InstanceType]:
    instance_types = []
    # XXX: remove query for location. This is shortcut for development phrase.
    for resource in client.resource_skus.list(filter=f"location eq '{location}'"):
        if resource.resource_type != "virtualMachines":
            continue
        if resource.restrictions:
            continue
        capabilities = {pair.name: pair.value for pair in resource.capabilities}
        if capabilities["CpuArchitectureType"] != "x64":
            continue
        gpus = []
        if "GPUs" in capabilities:
            # XXX: There is no way to get this from API.
            # https://github.com/Azure/azure-cli/issues/20077
            gpus = [Gpu(name="unknown", memory_mib=1)] * int(capabilities["GPUs"])
        instance_types.append(
            InstanceType(
                instance_name=resource.name,
                resources=Resources(
                    cpus=capabilities["vCPUs"],
                    memory_mib=float(capabilities["MemoryGB"]) * 1024,
                    gpus=gpus,
                    # XXX: Investigate a way to get stop virtual machines.
                    # https://learn.microsoft.com/en-us/azure/virtual-machines/spot-vms
                    interruptible=False,
                    local=False,
                ),
            )
        )

    return instance_types


# XXX: make this function common (base) for aws too. This is copy from aws.
def _get_instance_type(
    instance_types: List[InstanceType], requirements: Optional[Requirements]
) -> Optional[InstanceType]:
    instance_type = next(
        filter(lambda i: _matches(i.resources, requirements), instance_types),
        None,
    )
    if instance_type is None:
        return
    incorruptible = False
    if requirements and requirements.interruptible:
        raise NotImplementedError
        incorruptible = True
    return (
        InstanceType(
            instance_name=instance_type.instance_name,
            resources=Resources(
                cpus=instance_type.resources.cpus,
                memory_mib=instance_type.resources.memory_mib,
                gpus=instance_type.resources.gpus,
                interruptible=incorruptible,
                local=False,
            ),
        )
        if instance_type
        else None
    )
