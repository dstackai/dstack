from collections.abc import Iterable

from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.services.ssh.tunnel import SSH_DEFAULT_OPTIONS, SocketPair, SSHTunnel
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.instances import get_instance_remote_connection_info
from dstack._internal.server.services.jobs import get_job_provisioning_data, get_job_runtime_data
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.path import FileContent


def get_container_ssh_credentials(job: JobModel) -> list[tuple[SSHConnectionParams, FileContent]]:
    """
    Returns the information needed to connect to the SSH server inside the job container.

    The user of the target host (container) is set to:
        * VM-based backends and SSH instances: "root"
        * container-based backends: `JobProvisioningData.username`, which is, as of 2026-03-10,
        is always "root" on all supported backends (Runpod, Vast.ai, Kubernetes)

    Args:
        job: `JobModel` with `instance` and `instance.project` fields loaded.

    Returns:
        A list of hosts credentials as (host's `SSHConnectionParams`, private key's `FileContent`)
        pairs ordered from the first proxy jump (if any) to the target host (container).
    """
    hosts: list[tuple[SSHConnectionParams, FileContent]] = []

    instance = get_or_error(job.instance)
    project_key = FileContent(instance.project.ssh_private_key)

    rci = get_instance_remote_connection_info(instance)
    if rci is not None and (head_proxy := rci.ssh_proxy) is not None:
        head_key = FileContent(get_or_error(get_or_error(rci.ssh_proxy_keys)[0].private))
        hosts.append((head_proxy, head_key))

    jpd = get_job_provisioning_data(job)
    assert jpd is not None
    assert jpd.hostname is not None
    assert jpd.ssh_port is not None

    if jpd.dockerized:
        if jpd.backend != BackendType.LOCAL:
            instance_proxy = SSHConnectionParams(
                hostname=jpd.hostname,
                username=jpd.username,
                port=jpd.ssh_port,
            )
            hosts.append((instance_proxy, project_key))
        ssh_port = DSTACK_RUNNER_SSH_PORT
        jrd = get_job_runtime_data(job)
        if jrd is not None and jrd.ports is not None:
            ssh_port = jrd.ports.get(ssh_port, ssh_port)
        target_host = SSHConnectionParams(
            hostname="localhost",
            username="root",
            port=ssh_port,
        )
        hosts.append((target_host, project_key))
    else:
        if jpd.ssh_proxy is not None:
            hosts.append((jpd.ssh_proxy, project_key))
        target_host = SSHConnectionParams(
            hostname=jpd.hostname,
            username=jpd.username,
            port=jpd.ssh_port,
        )
        hosts.append((target_host, project_key))

    return hosts


def container_ssh_tunnel(
    job: JobModel,
    forwarded_sockets: Iterable[SocketPair] = (),
    options: dict[str, str] = SSH_DEFAULT_OPTIONS,
) -> SSHTunnel:
    """
    Build SSHTunnel for connecting to the container running the specified job.
    """
    hosts = get_container_ssh_credentials(job)
    target, identity = hosts[-1]
    return SSHTunnel(
        destination=f"{target.username}@{target.hostname}",
        port=target.port,
        ssh_proxies=hosts[:-1],
        identity=identity,
        forwarded_sockets=forwarded_sockets,
        options=options,
    )
