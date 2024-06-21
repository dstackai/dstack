from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume, VolumeProvisioningData
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class LocalCompute(Compute):
    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        return [
            InstanceOfferWithAvailability(
                backend=BackendType.LOCAL,
                instance=InstanceType(
                    name="local",
                    resources=Resources(cpus=4, memory_mib=8192, gpus=[], spot=False),
                ),
                region="local",
                price=0.00,
                availability=InstanceAvailability.AVAILABLE,
                instance_runtime=InstanceRuntime.RUNNER,
            )
        ]

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        pass

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> JobProvisioningData:
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id="local",
            hostname="127.0.0.1",
            internal_ip=None,
            region="",
            price=instance_offer.price,
            username="root",
            ssh_port=10022,
            ssh_proxy=None,
            dockerized=True,
            backend_data=None,
        )

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: List[Volume],
    ) -> JobProvisioningData:
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_type=instance_offer.instance,
            instance_id="local",
            hostname="127.0.0.1",
            internal_ip=None,
            region="",
            price=instance_offer.price,
            username="root",
            ssh_port=10022,
            ssh_proxy=None,
            dockerized=True,
            backend_data=None,
        )

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        return VolumeProvisioningData(
            volume_id=volume.name,
            size_gb=int(volume.configuration.size),
        )

    def delete_volume(self, volume: Volume):
        pass

    def attach_volume(self, volume: Volume, instance_id: str):
        pass

    def detach_volume(self, volume: Volume, instance_id: str):
        pass
