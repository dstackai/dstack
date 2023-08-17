import re
import subprocess
import time
from tempfile import NamedTemporaryFile
from typing import List, Optional

import pkg_resources

from dstack._internal.backend.base.compute import Compute
from dstack._internal.backend.base.head import (
    delete_head_object,
    list_head_objects,
    put_head_object,
)
from dstack._internal.backend.base.secrets import SecretsManager
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.error import SSHCommandError
from dstack._internal.core.gateway import GatewayHead
from dstack._internal.core.job import Job
from dstack._internal.utils.common import PathLike, removeprefix
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.interpolator import VariablesInterpolator
from dstack._internal.utils.random_names import generate_name


def create_gateway(compute: Compute, storage: Storage, ssh_key_pub: str) -> GatewayHead:
    # todo generate while instance name is not unique
    instance_name = f"dstack-gateway-{generate_name()}"
    head = compute.create_gateway(instance_name, ssh_key_pub)
    put_head_object(storage, head)
    return head


def list_gateways(storage: Storage) -> List[GatewayHead]:
    return list_head_objects(storage, GatewayHead)


def delete_gateway(compute: Compute, storage: Storage, instance_name: str):
    heads = list_gateways(storage)
    for head in heads:
        if head.instance_name != instance_name:
            continue
        compute.delete_instance(instance_name)
        delete_head_object(storage, head)


def resolve_hostname(secrets_manager: SecretsManager, repo_id: str, hostname: str) -> str:
    secrets = {}
    _, missed = VariablesInterpolator({}).interpolate(hostname, return_missing=True)
    for ns_name in missed:
        name = removeprefix(ns_name, "secrets.")
        value = secrets_manager.get_secret(repo_id, name)
        if value is not None:
            secrets[name] = value.secret_value
    return VariablesInterpolator({"secrets": secrets}).interpolate(hostname)


def publish(
    hostname: str,
    port: int,
    ssh_key: bytes,
    secure: bool,
    project_private_key: str,
    user: str = "ubuntu",
) -> str:
    command = ["sudo", "python3", "-", hostname, str(port), f'"{ssh_key.decode().strip()}"']
    if secure:
        command.append("--secure")
    script_path = pkg_resources.resource_filename("dstack._internal", "scripts/gateway_publish.py")
    with open(script_path, "r") as script, NamedTemporaryFile("w") as id_rsa:
        id_rsa.write(project_private_key)
        id_rsa.flush()
        output = exec_ssh_command(
            hostname, command=" ".join(command), user=user, id_rsa=id_rsa.name, stdin=script
        )
    return output.decode().strip()


def exec_ssh_command(
    hostname: str, command: str, user: str, id_rsa: Optional[PathLike], stdin=None
) -> bytes:
    args = ["ssh"]
    if id_rsa is not None:
        args += ["-i", id_rsa]
    args += [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        f"{user}@{hostname}",
        command,
    ]
    if not hostname:  # ssh hangs indefinitely with empty hostname
        raise SSHCommandError(
            args, "ssh: Could not connect to the gateway, because hostname is empty"
        )
    proc = subprocess.Popen(args, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        raise SSHCommandError(args, stderr.decode())
    return stdout


def setup_nginx_certbot() -> str:
    lines = [
        "sudo apt-get update",
        "DEBIAN_FRONTEND=noninteractive sudo apt-get install -y -q nginx",
        "sudo snap install --classic certbot",
        "sudo ln -s /snap/bin/certbot /usr/bin/certbot",
        "WWW_UID=$(id -u www-data)",
        "WWW_GID=$(id -g www-data)",
        "install -m 700 -o $WWW_UID -g $WWW_GID -d /var/www/.ssh",
        "install -m 600 -o $WWW_UID -g $WWW_GID /dev/null /var/www/.ssh/authorized_keys",
    ]
    return "\n".join(lines)


def is_ip_address(hostname: str) -> bool:
    return re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", hostname) is not None


def setup_service_job(job: Job, secrets_manager: SecretsManager, project_private_key: str) -> Job:
    job.gateway.hostname = resolve_hostname(
        secrets_manager, job.repo_ref.repo_id, job.gateway.hostname
    )
    job.gateway.secure = not is_ip_address(job.gateway.hostname)
    if job.gateway.secure and job.gateway.public_port == 80:
        job.gateway.public_port = 443
    private_bytes, public_bytes = generate_rsa_key_pair_bytes(comment=job.run_name)
    job.gateway.sock_path = publish(
        job.gateway.hostname,
        job.gateway.public_port,
        public_bytes,
        project_private_key=project_private_key,
        secure=job.gateway.secure,
    )
    job.gateway.ssh_key = private_bytes.decode()
    return job
