import io
import json
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List

import paramiko

from dstack._internal.core.errors import ProvisioningError
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceType,
    Resources,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


SSH_CONNECT_TIMEOUT = 10

DSTACK_SHIM_ENV_FILE = "dstack-shim.env"


def sftp_upload(client: paramiko.SSHClient, path: str, body: str) -> None:
    try:
        sftp = client.open_sftp()
        channel = sftp.get_channel()
        if channel is not None:
            channel.settimeout(10)
        sftp.putfo(io.BytesIO(body.encode()), path)
        sftp.close()
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError() from e


def upload_envs(client: paramiko.SSHClient, working_dir: str, envs: Dict[str, str]) -> None:
    envs["DSTACK_SERVICE_MODE"] = "1"  # make host_info.json on start
    dot_env = "\n".join(f'{key.upper()}="{value.strip()}"' for key, value in envs.items())
    tmp_file_path = f"/tmp/{DSTACK_SHIM_ENV_FILE}"
    sftp_upload(client, tmp_file_path, dot_env)
    try:
        cmd = f"sudo mkdir -p {working_dir} && sudo mv {tmp_file_path} {working_dir}/"
        _, stdout, stderr = client.exec_command(cmd, timeout=10)
        out = stdout.read().strip()
        err = stderr.read().strip()
        if out or err:
            logger.warning(
                "The command '%s' didn't work. stdout: %s, stderr: %s",
                tmp_file_path,
                out.decode(),
                err.decode(),
            )
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError() from e


def run_pre_start_commands(client: paramiko.SSHClient, shim_pre_start_commands: List[str]) -> None:
    script = " && ".join(shim_pre_start_commands)
    try:
        client.exec_command(f"sudo sh -c '{script}'", timeout=100)
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError() from e


def run_shim_as_systemd_service(client: paramiko.SSHClient, working_dir: str, dev: bool) -> None:
    dev_flag = "--dev" if dev else ""
    shim_service = f"""\
    [Unit]
    Description=dstack-shim
    After=network.target

    [Service]
    Type=simple
    User=root
    Restart=always
    WorkingDirectory={working_dir}
    EnvironmentFile={working_dir}/{DSTACK_SHIM_ENV_FILE}
    ExecStart=/usr/local/bin/dstack-shim {dev_flag} docker --keep-container
    StandardOutput=append:/root/.dstack/shim.log
    StandardError=append:/root/.dstack/shim.log

    [Install]
    WantedBy=multi-user.target
    """

    stripped_shim_service = "\n".join(line.strip() for line in shim_service.splitlines())
    sftp_upload(client, "/tmp/dstack-shim.service", stripped_shim_service)

    try:
        client.exec_command(
            "sudo mv /tmp/dstack-shim.service /etc/systemd/system/dstack-shim.service", timeout=10
        )
        client.exec_command("sudo systemctl daemon-reload", timeout=10)
        client.exec_command("sudo systemctl --no-block enable dstack-shim", timeout=10)
        client.exec_command("sudo systemctl start dstack-shim", timeout=10)

    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError() from e


def get_host_info(client: paramiko.SSHClient, working_dir: str) -> Dict[str, Any]:
    host_info = None
    # wait host_info
    retries = 60
    for _ in range(retries):
        try:
            _, stdout, _ = client.exec_command(
                f"sudo cat {working_dir}/host_info.json", timeout=10
            )
        except (paramiko.SSHException, OSError) as e:
            logger.debug("Cannot run `cat hostinfo.json` in the remote instance: %s", e)
        else:
            try:
                host_info_json = stdout.read()
                host_info = json.loads(host_info_json)
                return host_info
            except ValueError:  # JSON parse error
                _, stdout, _ = client.exec_command("sudo systemctl  status dstack-shim.service")
                status = stdout.read()
                for raw_line in status.splitlines():
                    line = raw_line.decode()
                    if line.strip().startswith("Active: failed"):
                        raise ProvisioningError("The dstack-shim service doesn't start")

        time.sleep(3)
    else:
        raise ProvisioningError("Cannot get host_info")


def host_info_to_instance_type(host_info: Dict[str, Any]) -> InstanceType:
    if host_info.get("gpu_count", 0):
        gpu_memory = int(host_info["gpu_memory"].lower().replace("mib", "").strip())
        gpus = [Gpu(name=host_info["gpu_name"], memory_mib=gpu_memory)] * host_info["gpu_count"]
    else:
        gpus = []
    instance_type = InstanceType(
        name="instance",
        resources=Resources(
            cpus=host_info["cpus"],
            memory_mib=host_info["memory"] / 1024 / 1024,
            spot=False,
            gpus=gpus,
            disk=Disk(size_mib=host_info["disk_size"] / 1024 / 1024),
        ),
    )
    return instance_type


@contextmanager
def get_paramiko_connection(
    ssh_user: str, host: str, port: int, pkeys: List[paramiko.PKey]
) -> Generator[paramiko.SSHClient, None, None]:
    with paramiko.SSHClient() as client:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        for pkey in pkeys:
            conn_url = f"{ssh_user}@{host}:{port}"
            try:
                logger.debug("Try to connect to %s with key %s", conn_url, pkey.fingerprint)
                client.connect(
                    username=ssh_user,
                    hostname=host,
                    port=port,
                    pkey=pkey,
                    look_for_keys=False,
                    allow_agent=False,
                    timeout=SSH_CONNECT_TIMEOUT,
                )
            except paramiko.AuthenticationException:
                continue  # try next key
            except (paramiko.SSHException, OSError) as e:
                raise ProvisioningError() from e
            else:
                yield client
                return
        else:
            keys_fp = ", ".join(f"{pk.fingerprint!r}" for pk in pkeys)
            raise ProvisioningError(
                f"SSH connection to the {conn_url} with keys [{keys_fp}] was unsuccessful"
            )
