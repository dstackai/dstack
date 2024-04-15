from typing import List, Optional

from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import (
    get_docker_commands,
    get_instance_name,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.runpod.api_client import RunpodApiClient
from dstack._internal.core.errors import (
    BackendError,
    ContainerTimeoutError,
    RunContainerError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceConfiguration,
    InstanceOfferWithAvailability,
    LaunchedInstanceInfo,
    SSHKey,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class RunpodCompute(Compute):
    def __init__(self, config):
        self.config = config
        self.api_client = RunpodApiClient(config.creds.api_key)

    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        offers = get_catalog_offers(
            backend=BackendType.RUNPOD,
            requirements=requirements,
        )
        offers = [
            InstanceOfferWithAvailability(
                **offer.dict(), availability=InstanceAvailability.AVAILABLE
            )
            for offer in offers
        ]
        return offers

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        instance_config = InstanceConfiguration(
            project_name=run.project_name,
            instance_name=get_instance_name(run, job),
            ssh_keys=[
                SSHKey(public=run.run_spec.ssh_key_pub.strip()),
                SSHKey(public=project_ssh_public_key.strip()),
            ],
            job_docker_config=None,
            user=run.user,
        )

        authorized_keys = instance_config.get_public_keys()
        memory_size = round(instance_offer.instance.resources.memory_mib / 1024)
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        resp = self.api_client.create_pod(
            name=instance_config.instance_name,
            image_name=job.job_spec.image_name,
            gpu_type_id=instance_offer.instance.name,
            cloud_type="ALL",  # ["ALL", "COMMUNITY", "SECURE"]:
            gpu_count=len(instance_offer.instance.resources.gpus),
            container_disk_in_gb=disk_size,
            min_vcpu_count=instance_offer.instance.resources.cpus,
            min_memory_in_gb=memory_size,
            support_public_ip=True,
            docker_args=get_docker_args(authorized_keys),
            ports="10022/tcp",
        )

        instance_id = resp["id"]
        # Wait until VM State is Active. This is necessary to get the ip_address.
        pod = self.api_client.wait_for_instance(instance_id)
        if pod is None:
            self.terminate_instance(instance_id, region="")
            raise ContainerTimeoutError(f"Wait instance {instance_id} timeout")

        if pod["runtime"].get("ports") is None:
            self.terminate_instance(instance_id, region="")
            raise RunContainerError(f"The instance {instance_id} failed to start")

        for port in pod["runtime"]["ports"]:
            if port["privatePort"] == 10022:
                ip = port["ip"]
                publicPort = port["publicPort"]
                break

        return LaunchedInstanceInfo(
            instance_id=instance_id,
            ip_address=ip.strip(),
            region=instance_offer.region,
            username="root",
            ssh_port=int(publicPort),
            dockerized=False,
            ssh_proxy=None,
            backend_data=None,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
        try:
            self.api_client.terminate_pod(instance_id)
        except BackendError as e:
            if e.args[0] == "Instance Not Found":
                logger.debug("The instance with name %s not found", instance_id)
                return
            raise


def get_docker_args(authorized_keys):
    commands = get_docker_commands(authorized_keys, False)
    command = " && ".join(commands)
    command_escaped = command.replace('"', '\\"')
    command_escaped = command_escaped.replace("'", '\\"')
    command_escaped = command_escaped.replace("\n", "\\n")
    return f"bash -c '{command_escaped}'"
