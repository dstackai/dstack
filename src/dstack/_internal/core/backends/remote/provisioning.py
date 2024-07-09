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
from dstack._internal.utils.gpu import convert_gpu_name
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
        raise ProvisioningError(f"sft_upload failed: {e}") from e


def upload_envs(client: paramiko.SSHClient, working_dir: str, envs: Dict[str, str]) -> None:
    envs["DSTACK_SERVICE_MODE"] = "1"  # make host_info.json on start
    dot_env = "\n".join(f'{key.upper()}="{value.strip()}"' for key, value in envs.items())
    tmp_file_path = f"/tmp/{DSTACK_SHIM_ENV_FILE}"
    sftp_upload(client, tmp_file_path, dot_env)
    try:
        cmd = f"sudo mkdir -p {working_dir} && sudo mv {tmp_file_path} {working_dir}/"
        _, stdout, stderr = client.exec_command(cmd, timeout=20)
        out = stdout.read().strip().decode()
        err = stderr.read().strip().decode()
        if out or err:
            raise ProvisioningError(
                f"The command 'upload_envs' didn't work. stdout: {out}, stderr: {err}"
            )
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError(f"upload_envs failed: {e}") from e


def run_pre_start_commands(
    client: paramiko.SSHClient, shim_pre_start_commands: List[str], authorized_keys: List[str]
) -> None:
    try:
        authorized_keys_content = "\n".join(authorized_keys).strip()
        _, stdout, stderr = client.exec_command(
            f"echo '\n{authorized_keys_content}' >> ~/.ssh/authorized_keys", timeout=5
        )
        out = stdout.read().strip().decode()
        err = stderr.read().strip().decode()
        if out or err:
            raise ProvisioningError(
                f"The command 'authorized_keys' didn't work. stdout: {out}, stderr: {err}"
            )
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError(f"upload authorized_keys failed: {e}") from e

    script = " && ".join(shim_pre_start_commands)
    try:
        _, stdout, stderr = client.exec_command(f"sudo sh -c '{script}'", timeout=120)
        out = stdout.read().strip().decode()
        err = stderr.read().strip().decode()
        if out or err:
            raise ProvisioningError(
                f"The command 'run_pre_start_commands' didn't work. stdout: {out}, stderr: {err}"
            )
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError(f"run_pre-start_commands failed: {e}") from e


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
        cmd = """\
            sudo mv /tmp/dstack-shim.service /etc/systemd/system/dstack-shim.service && \
            sudo systemctl daemon-reload && \
            sudo systemctl --quiet enable dstack-shim && \
            sudo systemctl restart dstack-shim
        """
        _, stdout, stderr = client.exec_command(cmd, timeout=100)
        out = stdout.read().strip().decode()
        err = stderr.read().strip().decode()
        if out or err:
            raise ProvisioningError(
                f"The command 'run_shim_as_systemd_service' didn't work. stdout: {out}, stderr: {err}"
            )
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError(f"run_shim_as_systemd failed: {e}") from e


def check_dstack_shim_service(client: paramiko.SSHClient):
    try:
        _, stdout, _ = client.exec_command("sudo systemctl status dstack-shim.service", timeout=10)
        status = stdout.read()
    except (paramiko.SSHException, OSError) as e:
        raise ProvisioningError(f"Checking dstack-shim.service status failed: {e}") from e

    for raw_line in status.splitlines():
        line = raw_line.decode()
        if line.strip().startswith("Active: failed"):
            raise ProvisioningError(f"The dstack-shim service doesn't start: {line.strip()}")


def get_host_info(client: paramiko.SSHClient, working_dir: str) -> Dict[str, Any]:
    # wait host_info
    retries = 60
    iter_delay = 3
    for _ in range(retries):
        try:
            _, stdout, stderr = client.exec_command(
                f"sudo cat {working_dir}/host_info.json", timeout=10
            )
            err = stderr.read().decode().strip()
            if err:
                logger.debug("Retry after error: %s", err)
                time.sleep(iter_delay)
                continue
        except (paramiko.SSHException, OSError) as e:
            logger.debug("Cannot run `cat host_info.json` in the remote instance: %s", e)
        else:
            try:
                host_info_json = stdout.read()
                host_info = json.loads(host_info_json)
                return host_info
            except ValueError:  # JSON parse error
                check_dstack_shim_service(client)
                raise ProvisioningError("Cannot parse host_info")
        time.sleep(iter_delay)
    else:
        check_dstack_shim_service(client)
        raise ProvisioningError("Cannot get host_info")


def get_shim_healthcheck(client: paramiko.SSHClient) -> str:
    retries = 20
    iter_delay = 3
    for _ in range(retries):
        try:
            _, stdout, stderr = client.exec_command(
                "curl -s http://localhost:10998/api/healthcheck", timeout=15
            )
            out = stdout.read().strip().decode()
            err = stderr.read().strip().decode()
            if err:
                raise ProvisioningError(
                    f"The command 'get_shim_healthcheck' didn't work. stdout: {out}, stderr: {err}"
                )
            if not out:
                logger.debug("healthcheck is empty. retry")
                time.sleep(iter_delay)
                continue
            return out
        except (paramiko.SSHException, OSError) as e:
            raise ProvisioningError(f"get_shim_healthcheck failed: {e}") from e


def host_info_to_instance_type(host_info: Dict[str, Any]) -> InstanceType:
    gpu_name = convert_gpu_name(host_info["gpu_name"])
    if host_info.get("gpu_count", 0):
        gpu_memory = int(host_info["gpu_memory"].lower().replace("mib", "").strip())
        gpus = [Gpu(name=gpu_name, memory_mib=gpu_memory)] * host_info["gpu_count"]
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
                logger.debug(
                    f'Authentication faild to connect to "{conn_url}" and {pkey.fingerprint}'
                )
                continue  # try next key
            except (paramiko.SSHException, OSError) as e:
                raise ProvisioningError(f"Connect failed: {e}") from e
            else:
                yield client
                return
        else:
            keys_fp = ", ".join(f"{pk.fingerprint!r}" for pk in pkeys)
            raise ProvisioningError(
                f"SSH connection to the {conn_url} with keys [{keys_fp}] was unsuccessful"
            )
