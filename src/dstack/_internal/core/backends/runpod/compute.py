from typing import List, Optional

from dstack._internal import settings
from dstack._internal.core.backends.base import Compute
from dstack._internal.core.backends.base.compute import (
    get_dstack_runner_version,
    get_instance_name,
)
from dstack._internal.core.backends.base.offers import get_catalog_offers
from dstack._internal.core.backends.runpod.api_client import RunpodApiClient
from dstack._internal.core.errors import BackendError, ComputeError
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
        launched_instance_info = self.create_instance(instance_offer, instance_config)
        return launched_instance_info

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> LaunchedInstanceInfo:
        authorized_keys = instance_config.get_public_keys()
        memory_size = round(instance_offer.instance.resources.memory_mib / 1024)
        disk_size = round(instance_offer.instance.resources.disk.size_mib / 1024)
        resp = self.api_client.create_pod(
            name=instance_config.instance_name,
            image_name="runpod/pytorch:2.1.1-py3.10-cuda12.1.1-devel-ubuntu22.04",
            gpu_type_id=instance_offer.instance.name,
            cloud_type="ALL",  # ["ALL", "COMMUNITY", "SECURE"]:
            gpu_count=len(instance_offer.instance.resources.gpus),
            container_disk_in_gb=disk_size,
            min_vcpu_count=instance_offer.instance.resources.cpus,
            min_memory_in_gb=memory_size,
            support_public_ip=True,
            docker_args=get_docker_args(authorized_keys),
            ports="22/tcp",
        )

        instance_id = resp["id"]
        # Wait until VM State is Active. This is necessary to get the ip_address.
        pod = self.api_client.wait_for_instance(instance_id)
        if pod is None:
            raise ComputeError(f"Wait instance {instance_id} timeout")

        for port in pod["runtime"]["ports"]:
            if port["privatePort"] == 22:
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
    authorized_keys_content = "\\n".join(authorized_keys).strip()
    update_and_setup_ssh = f'apt update; DEBIAN_FRONTEND=noninteractive apt-get install openssh-server -y;mkdir -p ~/.ssh;cd $_;chmod 700 ~/.ssh;echo \\"{authorized_keys_content}\\" >> authorized_keys;chmod 700 authorized_keys'
    env_cmd = "env >> ~/.ssh/environment"
    sed_cmd = r"sed -ie \"1s@^@export PATH=\\\"''$PATH'':\\$PATH\\\"\\n\\n@\" ~/.profile"
    rm_rf = "rm -rf /etc/ssh/ssh_host_*"
    ssh_key_gen = "ssh-keygen -A > /dev/null"
    runner = "/usr/local/bin/dstack-runner"

    build = get_dstack_runner_version()
    bucket = "dstack-runner-downloads-stgn"
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"
    url = f"https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-runner-linux-amd64"

    runner_commands = [
        f'curl --connect-timeout 60 --max-time 240 --retry 1 --output {runner} \\"{url}\\"',
        f"chmod +x {runner}",
        f"{runner} --log-level 6 start --http-port 10999 --temp-dir /tmp/runner --home-dir /root --working-dir /workflow",
    ]
    runner_commands = " && ".join(runner_commands)

    return f"bash -c '{update_and_setup_ssh} && {env_cmd} && {sed_cmd} && {rm_rf} && {ssh_key_gen} && service ssh start && {runner_commands}; sleep infinity'"
