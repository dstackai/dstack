import os
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Dict, List, Optional

import git
import requests
import yaml

from dstack._internal import settings
from dstack._internal.core.models.gateways import (
    GatewayComputeConfiguration,
    GatewayProvisioningData,
)
from dstack._internal.core.models.instances import (
    InstanceConfiguration,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.placement import PlacementGroup, PlacementGroupProvisioningData
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import (
    Volume,
    VolumeAttachmentData,
    VolumeProvisioningData,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

DSTACK_WORKING_DIR = "/root/.dstack"


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
        volumes: List[Volume],
    ) -> JobProvisioningData:
        """
        Launches a new instance for the job. It should return `JobProvisioningData` ASAP.
        If required to wait to get the IP address or SSH port, return partially filled `JobProvisioningData`
        and implement `update_provisioning_data()`.
        """
        pass

    @abstractmethod
    def terminate_instance(
        self,
        instance_id: str,
        region: str,
        backend_data: Optional[str] = None,
    ) -> None:
        """
        Terminates an instance by `instance_id`.
        If the instance does not exist, it should not raise errors but return silently.
        """
        pass

    def create_instance(
        self,
        instance_offer: InstanceOfferWithAvailability,
        instance_config: InstanceConfiguration,
    ) -> JobProvisioningData:
        """
        Launches a new instance. It should return `JobProvisioningData` ASAP.
        If required to wait to get the IP address or SSH port, return partially filled `JobProvisioningData`
        and implement `update_provisioning_data()`.
        """
        raise NotImplementedError()

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        """
        This method is called if `JobProvisioningData` returned from `run_job()`/`create_instance()`
        is not complete, e.g. missing `hostname` or `ssh_port`.
        It can be used if getting complete provisioning data takes a long of time.
        It should not wait but return immediately.
        If it raises `ProvisioningError`, there will be no further attempts to update the provisioning data,
        and the run will be terminated.
        """
        pass

    def create_placement_group(
        self,
        placement_group: PlacementGroup,
    ) -> PlacementGroupProvisioningData:
        """
        Creates a placement group.
        """
        raise NotImplementedError()

    def delete_placement_group(
        self,
        placement_group: PlacementGroup,
    ):
        """
        Deletes a placement group.
        If the group does not exist, it should not raise errors but return silently.
        """
        raise NotImplementedError()

    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> GatewayProvisioningData:
        """
        Creates a gateway instance.
        """
        raise NotImplementedError()

    def terminate_gateway(
        self,
        instance_id: str,
        configuration: GatewayComputeConfiguration,
        backend_data: Optional[str] = None,
    ):
        """
        Terminates a gateway instance. Generally, it passes the call to `terminate_instance()`,
        but may perform additional work such as deleting a load balancer when a gateway has one.
        """
        raise NotImplementedError()

    def register_volume(self, volume: Volume) -> VolumeProvisioningData:
        """
        Returns VolumeProvisioningData for an existing volume.
        Used to add external volumes to dstack.
        """
        raise NotImplementedError()

    def create_volume(self, volume: Volume) -> VolumeProvisioningData:
        """
        Creates a new volume.
        """
        raise NotImplementedError()

    def delete_volume(self, volume: Volume):
        """
        Deletes a volume.
        """
        raise NotImplementedError()

    def attach_volume(self, volume: Volume, instance_id: str) -> VolumeAttachmentData:
        """
        Attaches a volume to the instance.
        If the volume is not found, it should raise `ComputeError()` instead of a thrid-party exception.
        """
        raise NotImplementedError()

    def detach_volume(self, volume: Volume, instance_id: str):
        """
        Detaches a volume from the instance.
        """
        raise NotImplementedError()


def get_instance_name(run: Run, job: Job) -> str:
    return f"{run.project_name.lower()}-{job.job_spec.job_name}"


def get_cloud_config(**config) -> str:
    return "#cloud-config\n" + yaml.dump(config, default_flow_style=False)


def get_user_data(
    authorized_keys: List[str], backend_specific_commands: Optional[List[str]] = None
) -> str:
    shim_commands = get_shim_commands(authorized_keys)
    commands = (backend_specific_commands or []) + shim_commands
    return get_cloud_config(
        runcmd=[["sh", "-c", " && ".join(commands)]],
        ssh_authorized_keys=authorized_keys,
    )


def get_shim_env(authorized_keys: List[str]) -> Dict[str, str]:
    envs = {
        "DSTACK_RUNNER_LOG_LEVEL": "6",
        "DSTACK_RUNNER_DOWNLOAD_URL": get_dstack_runner_download_url(),
        "DSTACK_PUBLIC_SSH_KEY": "\n".join(authorized_keys),
        "DSTACK_HOME": DSTACK_WORKING_DIR,
    }
    return envs


def get_shim_commands(
    authorized_keys: List[str], *, is_privileged: bool = False, pjrt_device: Optional[str] = None
) -> List[str]:
    commands = get_shim_pre_start_commands()
    for k, v in get_shim_env(authorized_keys).items():
        commands += [f'export "{k}={v}"']
    commands += get_run_shim_script(is_privileged, pjrt_device)
    return commands


def get_dstack_runner_version() -> str:
    if settings.DSTACK_VERSION is not None:
        return settings.DSTACK_VERSION
    version = os.environ.get("DSTACK_RUNNER_VERSION", None)
    if version is None and settings.DSTACK_USE_LATEST_FROM_BRANCH:
        version = get_latest_runner_build()
    return version or "latest"


def get_dstack_runner_download_url() -> str:
    if url := os.environ.get("DSTACK_RUNNER_DOWNLOAD_URL"):
        return url
    build = get_dstack_runner_version()
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"
    else:
        bucket = "dstack-runner-downloads-stgn"
    return (
        f"https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-runner-linux-amd64"
    )


def get_dstack_shim_download_url() -> str:
    if url := os.environ.get("DSTACK_SHIM_DOWNLOAD_URL"):
        return url
    build = get_dstack_runner_version()
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"
    else:
        bucket = "dstack-runner-downloads-stgn"
    return f"https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-shim-linux-amd64"


def get_shim_pre_start_commands() -> List[str]:
    url = get_dstack_shim_download_url()
    dstack_shim_binary_name = "dstack-shim"
    dstack_shim_binary_path = f"/usr/local/bin/{dstack_shim_binary_name}"

    return [
        f"dlpath=$(sudo mktemp -t {dstack_shim_binary_name}.XXXXXXXXXX)",
        # -sS -- disable progress meter and warnings, but still show errors (unlike bare -s)
        f'sudo curl -sS --compressed --connect-timeout 60 --max-time 240 --retry 1 --output "$dlpath" "{url}"',
        f'sudo mv "$dlpath" {dstack_shim_binary_path}',
        f"sudo chmod +x {dstack_shim_binary_path}",
        f"sudo mkdir {DSTACK_WORKING_DIR} -p",
    ]


def get_run_shim_script(is_privileged: bool, pjrt_device: Optional[str]) -> List[str]:
    privileged_flag = "--privileged" if is_privileged else ""
    pjrt_device_env = f"--pjrt-device={pjrt_device}" if pjrt_device else ""

    return [
        f"nohup dstack-shim docker {privileged_flag} {pjrt_device_env} >{DSTACK_WORKING_DIR}/shim.log 2>&1 &",
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


def get_docker_commands(
    authorized_keys: List[str], fix_path_in_dot_profile: bool = True
) -> List[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    commands = [
        # save and unset ld.so variables
        "_LD_LIBRARY_PATH=${LD_LIBRARY_PATH-} && unset LD_LIBRARY_PATH",
        "_LD_PRELOAD=${LD_PRELOAD-} && unset LD_PRELOAD",
        # common functions
        '_exists() { command -v "$1" > /dev/null 2>&1; }',
        # TODO(#1535): support non-root images properly
        "mkdir -p /root && chown root:root /root && export HOME=/root",
        # package manager detection/abstraction
        "_install() { NAME=Distribution; test -f /etc/os-release && . /etc/os-release; echo $NAME not supported; exit 11; }",
        'if _exists apt-get; then _install() { apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "$1"; }; fi',
        'if _exists yum; then _install() { yum install -y "$1"; }; fi',
        # check in sshd is here, install if not
        "if ! _exists sshd; then _install openssh-server; fi",
        # install curl if necessary
        "if ! _exists curl; then _install curl; fi",
        # prohibit password authentication
        'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
        # create ssh dirs and add public key
        "mkdir -p /run/sshd ~/.ssh",
        "chmod 700 ~/.ssh",
        f"echo '{authorized_keys_content}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # preserve environment variables for SSH clients
        "env >> ~/.ssh/environment",
        "sed -ie '1s@^@export PATH=\"'\"$PATH\"':$PATH\"\\n\\n@' ~/.profile"
        if fix_path_in_dot_profile
        else ":",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # Ensure that PRIVSEP_PATH 1) exists 2) empty 3) owned by root,
        # see https://github.com/dstackai/dstack/issues/1999
        # /run/sshd is used in Debian-based distros, including Ubuntu:
        # https://salsa.debian.org/ssh-team/openssh/-/blob/debian/1%259.7p1-7/debian/rules#L60
        # /var/empty is the default path if not configured via ./configure --with-privsep-path=...
        "rm -rf /run/sshd && mkdir -p /run/sshd && chown root:root /run/sshd",
        "rm -rf /var/empty && mkdir -p /var/empty && chown root:root /var/empty",
        # start sshd
        "/usr/sbin/sshd -p 10022 -o PermitUserEnvironment=yes",
        # restore ld.so variables
        'if [ -n "$_LD_LIBRARY_PATH" ]; then export LD_LIBRARY_PATH="$_LD_LIBRARY_PATH"; fi',
        'if [ -n "$_LD_PRELOAD" ]; then export LD_PRELOAD="$_LD_PRELOAD"; fi',
    ]

    runner = "/usr/local/bin/dstack-runner"

    build = get_dstack_runner_version()
    bucket = "dstack-runner-downloads-stgn"
    if settings.DSTACK_VERSION is not None:
        bucket = "dstack-runner-downloads"

    url = f"https://{bucket}.s3.eu-west-1.amazonaws.com/{build}/binaries/dstack-runner-linux-amd64"

    commands += [
        f"curl --connect-timeout 60 --max-time 240 --retry 1 --output {runner} {url}",
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
        timeout=10,
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
        r = requests.get(f"{base_url}/latest-version", timeout=5)
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


def merge_tags(tags: Dict[str, str], backend_tags: Optional[Dict[str, str]]) -> Dict[str, str]:
    res = tags.copy()
    if backend_tags is not None:
        for k, v in backend_tags.items():
            res.setdefault(k, v)
    return res
