from typing import List, Optional

from dstack._internal.core.backends.base.compute import Compute, get_dstack_runner_version
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceType,
    LaunchedInstanceInfo,
    Resources,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
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
            )
        ]

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        pass

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        authorized_keys = f"{run.run_spec.ssh_key_pub.strip()}\\n{project_ssh_public_key.strip()}"
        logger.info(
            "Running job in LocalBackend. To start processing, run: `"
            f"DSTACK_BACKEND=local "
            "DSTACK_RUNNER_LOG_LEVEL=6 "
            f"DSTACK_RUNNER_VERSION={get_dstack_runner_version()} "
            f"DSTACK_IMAGE_NAME={job.job_spec.image_name} "
            f'DSTACK_PUBLIC_SSH_KEY="{authorized_keys}" ./shim --dev docker --keep-container`',
        )
        return LaunchedInstanceInfo(
            instance_id="local",
            ip_address="127.0.0.1",
            region="",
            username="root",
            ssh_port=10022,
            dockerized=False,
            ssh_proxy=None,
            backend_data=None,
        )
