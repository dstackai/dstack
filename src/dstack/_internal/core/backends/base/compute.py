import os
import re
from abc import ABC, abstractmethod
from typing import List, Optional

import git
import requests
import yaml

from dstack import version
from dstack._internal import settings
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import (
    InstanceOfferWithAvailability,
    InstanceState,
    LaunchedGatewayInfo,
    LaunchedInstanceInfo,
)
from dstack._internal.core.models.runs import Job, Requirements, Run
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class Compute(ABC):
    @abstractmethod
    def get_offers(
        self, requirements: Optional[Requirements] = None
    ) -> List[InstanceOfferWithAvailability]:
        pass

    @abstractmethod
    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ) -> LaunchedInstanceInfo:
        pass

    @abstractmethod
    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        pass

    def get_instance_state(self, instance_id: str, region: str) -> InstanceState:
        pass

    def create_gateway(
        self,
        instance_name: str,
        ssh_key_pub: str,
        region: str,
        project_id: str,
    ) -> LaunchedGatewayInfo:
        raise NotImplementedError()


def get_instance_name(run: Run, job: Job) -> str:
    return f"{run.project_name}-{job.job_spec.job_name}"


def get_user_data(
    backend: BackendType,
    image_name: str,
    authorized_keys: List[str],
    registry_auth_required: bool,
    cloud_config_kwargs: Optional[dict] = None,
) -> str:
    commands = get_shim_commands(
        backend=backend,
        image_name=image_name,
        authorized_keys=authorized_keys,
        registry_auth_required=registry_auth_required,
    )
    return get_cloud_config(
        runcmd=[["sh", "-c", " && ".join(commands)]],
        ssh_authorized_keys=authorized_keys,
        **(cloud_config_kwargs or {}),
    )


def get_shim_commands(
    backend: BackendType,
    image_name: str,
    authorized_keys: List[str],
    registry_auth_required: bool,
) -> List[str]:
    build = get_dstack_runner_version()
    env = {
        "DSTACK_BACKEND": backend.value,
        "DSTACK_RUNNER_LOG_LEVEL": "6",
        "DSTACK_RUNNER_VERSION": build,
        "DSTACK_IMAGE_NAME": image_name,
        "DSTACK_PUBLIC_SSH_KEY": "\n".join(authorized_keys),
        "DSTACK_HOME": "/root/.dstack",
    }
    commands = get_dstack_shim(build)
    for k, v in env.items():
        commands += [f'export "{k}={v}"']
    commands += get_run_shim_script(registry_auth_required)
    return commands


def get_dstack_runner_version() -> str:
    if settings.DSTACK_VERSION is not None:
        return settings.DSTACK_VERSION
    return os.environ.get("DSTACK_RUNNER_VERSION", None) or get_latest_runner_build() or "latest"


def get_cloud_config(**config) -> str:
    return "#cloud-config\n" + yaml.dump(config, default_flow_style=False)


def get_dstack_shim(build: str) -> List[str]:
    bucket = "dstack-runner-downloads-stgn"
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"

    return [
        f'sudo curl --output /usr/local/bin/dstack-shim "https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-shim-linux-amd64"',
        "sudo chmod +x /usr/local/bin/dstack-shim",
    ]


def get_run_shim_script(registry_auth_required: bool) -> List[str]:
    dev_flag = "" if settings.DSTACK_VERSION is not None else "--dev"
    with_auth_flag = "--with-auth" if registry_auth_required else ""
    return [
        f"nohup dstack-shim {dev_flag} docker {with_auth_flag} --keep-container >/root/shim.log 2>&1 &"
    ]


def get_gateway_user_data(authorized_key: str) -> str:
    return get_cloud_config(
        package_update=True,
        packages=[
            "nginx",
            "python3.10-venv",
        ],
        snap={"commands": [["install", "--classic", "certbot"]]},
        runcmd=[
            ["ln", "-s", "/snap/bin/certbot", "/usr/bin/certbot"],
            [
                "sed",
                "-i",
                "s/# server_names_hash_bucket_size 64;/server_names_hash_bucket_size 128;/",
                "/etc/nginx/nginx.conf",
            ],
            ["su", "ubuntu", "-c", " && ".join(get_dstack_gateway_commands())],
        ],
        ssh_authorized_keys=[authorized_key],
    )


def get_docker_commands(authorized_keys: List[str]) -> List[str]:
    authorized_keys = "\n".join(authorized_keys).strip()
    commands = [
        # note: &> redirection doesn't work in /bin/sh
        # check in sshd is here, install if not
        (
            "if ! command -v sshd >/dev/null 2>&1; then { "
            "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server; "
            "} || { "
            "yum -y install openssh-server; "
            "}; fi"
        ),
        # prohibit password authentication
        'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
        # create ssh dirs and add public key
        "mkdir -p /run/sshd ~/.ssh",
        "chmod 700 ~/.ssh",
        f"echo '{authorized_keys}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # preserve environment variables for SSH clients
        "env >> ~/.ssh/environment",
        'echo "export PATH=$PATH" >> ~/.profile',
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        "/usr/sbin/sshd -p 10022 -o PermitUserEnvironment=yes",
    ]
    build = get_dstack_runner_version()
    runner = "/usr/local/bin/dstack-runner"
    bucket = "dstack-runner-downloads-stgn"
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"
    commands += [
        f'curl --output {runner} "https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-runner-linux-amd64"',
        f"chmod +x {runner}",
        f"{runner} --log-level 6 start --http-port 10999 --temp-dir /tmp/runner --home-dir /root --working-dir /workflow",
    ]
    return commands


def get_latest_runner_build() -> Optional[str]:
    owner_repo = "dstackai/dstack"
    workflow_id = "build.yml"
    version_offset = 150

    repo = git.Repo(os.path.abspath(os.path.dirname(__file__)), search_parent_directories=True)
    for remote in repo.remotes:
        if re.search(rf"[@/]github\.com[:/]{owner_repo}\.", remote.url):
            break
    else:
        return None

    resp = requests.get(
        f"https://api.github.com/repos/{owner_repo}/actions/workflows/{workflow_id}/runs",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        params={
            "status": "success",
        },
    )
    resp.raise_for_status()

    head = repo.head.commit
    for run in resp.json()["workflow_runs"]:
        try:
            if repo.is_ancestor(run["head_sha"], head):
                ver = str(run["run_number"] + version_offset)
                logger.debug(f"Found the latest runner build: %s", ver)
                return ver
        except git.GitCommandError as e:
            if "Not a valid commit name" not in e.stderr:
                raise
    return None


def get_dstack_gateway_wheel(build: str) -> str:
    channel = "release" if version.__is_release__ else "stgn"
    return f"https://dstack-gateway-downloads.s3.amazonaws.com/{channel}/dstack_gateway-{build}-py3-none-any.whl"


def get_dstack_gateway_commands() -> List[str]:
    build = get_dstack_runner_version()
    if build == "latest":
        raise ValueError("`latest` is not appropriate version for a gateway")
    return [
        "mkdir -p /home/ubuntu/dstack",
        "python3 -m venv /home/ubuntu/dstack/blue",
        "python3 -m venv /home/ubuntu/dstack/green",
        f"/home/ubuntu/dstack/blue/bin/pip install {get_dstack_gateway_wheel(build)}",
        "sudo /home/ubuntu/dstack/blue/bin/python -m dstack.gateway.systemd install --run",
    ]
