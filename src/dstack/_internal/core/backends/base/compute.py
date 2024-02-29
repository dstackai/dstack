import os
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, List, Optional

import git
import requests
import yaml

from dstack._internal import settings
from dstack._internal.core.models.instances import (
    InstanceConfiguration,
    InstanceOfferWithAvailability,
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

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> LaunchedInstanceInfo:
        raise NotImplementedError()

    @abstractmethod
    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ) -> None:
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
    authorized_keys: List[str],
    cloud_config_kwargs: Optional[Dict[Any, Any]] = None,
) -> str:
    commands = get_shim_commands(authorized_keys)
    return get_cloud_config(
        runcmd=[["sh", "-c", " && ".join(commands)]],
        ssh_authorized_keys=authorized_keys,
        **(cloud_config_kwargs or {}),
    )


def get_shim_commands(authorized_keys: List[str]) -> List[str]:
    build = get_dstack_runner_version()
    env = {
        "DSTACK_RUNNER_LOG_LEVEL": "6",
        "DSTACK_RUNNER_VERSION": build,
        "DSTACK_PUBLIC_SSH_KEY": "\n".join(authorized_keys),
        "DSTACK_HOME": "/root/.dstack",
    }
    commands = get_dstack_shim(build)
    for k, v in env.items():
        commands += [f'export "{k}={v}"']
    commands += get_run_shim_script()
    return commands


def get_dstack_runner_version() -> str:
    if settings.DSTACK_VERSION is not None:
        return settings.DSTACK_VERSION
    version = os.environ.get("DSTACK_RUNNER_VERSION", None)
    if version is None and settings.DSTACK_USE_LATEST_FROM_BRANCH:
        version = get_latest_runner_build()
    return version or "latest"


def get_cloud_config(**config) -> str:
    return "#cloud-config\n" + yaml.dump(config, default_flow_style=False)


def get_dstack_shim(build: str) -> List[str]:
    bucket = "dstack-runner-downloads-stgn"
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"

    url = f"https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-shim-linux-amd64"

    return [
        f'sudo curl --connect-timeout 60 --max-time 240 --retry 1 --output /usr/local/bin/dstack-shim "{url}"',
        "sudo chmod +x /usr/local/bin/dstack-shim",
    ]


def get_run_shim_script() -> List[str]:
    dev_flag = "" if settings.DSTACK_VERSION is not None else "--dev"
    return [f"nohup dstack-shim {dev_flag} docker --keep-container >/root/shim.log 2>&1 &"]


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
    authorized_keys_content = "\n".join(authorized_keys).strip()
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
        f"echo '{authorized_keys_content}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # preserve environment variables for SSH clients
        "env >> ~/.ssh/environment",
        "sed -ie '1s@^@export PATH=\"'\"$PATH\"':$PATH\"\\n\\n@' ~/.profile",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        "/usr/sbin/sshd -p 10022 -o PermitUserEnvironment=yes",
    ]

    runner = "/usr/local/bin/dstack-runner"

    build = get_dstack_runner_version()
    bucket = "dstack-runner-downloads-stgn"
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"

    url = f"https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-runner-linux-amd64"

    commands += [
        f'curl --connect-timeout 60 --max-time 240 --retry 1 --output {runner} "{url}"',
        f"chmod +x {runner}",
        f"{runner} --log-level 6 start --http-port 10999 --temp-dir /tmp/runner --home-dir /root --working-dir /workflow",
    ]
    return commands


@lru_cache()  # Restart the server to find the latest build
def get_latest_runner_build() -> Optional[str]:
    owner_repo = "dstackai/dstack"
    workflow_id = "build.yml"
    version_offset = 150

    try:
        repo = git.Repo(os.path.abspath(os.path.dirname(__file__)), search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        return None
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
                logger.debug("Found the latest runner build: %s", ver)
                return ver
        except git.GitCommandError as e:
            if "Not a valid commit name" not in e.stderr:
                raise
    return None


def get_dstack_gateway_wheel(build: str) -> str:
    channel = "release" if settings.DSTACK_RELEASE else "stgn"
    base_url = f"https://dstack-gateway-downloads.s3.amazonaws.com/{channel}"
    if build == "latest":
        r = requests.get(f"{base_url}/latest-version")
        r.raise_for_status()
        build = r.text.strip()
        logger.debug("Found the latest gateway build: %s", build)
    return f"{base_url}/dstack_gateway-{build}-py3-none-any.whl"


def get_dstack_gateway_commands() -> List[str]:
    build = get_dstack_runner_version()
    return [
        "mkdir -p /home/ubuntu/dstack",
        "python3 -m venv /home/ubuntu/dstack/blue",
        "python3 -m venv /home/ubuntu/dstack/green",
        f"/home/ubuntu/dstack/blue/bin/pip install {get_dstack_gateway_wheel(build)}",
        "sudo /home/ubuntu/dstack/blue/bin/python -m dstack.gateway.systemd install --run",
    ]
