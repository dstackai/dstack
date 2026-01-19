from typing import Optional

from packaging.version import Version

from dstack._internal.core.models.instances import InstanceAvailability
from dstack._internal.server.schemas.gpus import ListGpusResponse


def patch_list_gpus_response(
    response: ListGpusResponse, client_version: Optional[Version]
) -> None:
    if client_version is None:
        return
    # CLIs prior to 0.20.4 incorrectly display the `no_balance` availability in `dstack offer --group-by gpu`
    if client_version < Version("0.20.4"):
        for gpu in response.gpus:
            if InstanceAvailability.NO_BALANCE in gpu.availability:
                gpu.availability = [
                    a for a in gpu.availability if a != InstanceAvailability.NO_BALANCE
                ]
                if InstanceAvailability.NOT_AVAILABLE not in gpu.availability:
                    gpu.availability.append(InstanceAvailability.NOT_AVAILABLE)
