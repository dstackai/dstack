from collections.abc import Iterable
from typing import Optional

import dstack._internal.server.services.jobs as jobs_services
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.instances import RemoteConnectionInfo, SSHConnectionParams
from dstack._internal.core.models.runs import JobProvisioningData
from dstack._internal.core.services.ssh.tunnel import SSH_DEFAULT_OPTIONS, SocketPair, SSHTunnel
from dstack._internal.server.models import JobModel
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.path import FileContent


def container_ssh_tunnel(
    job: JobModel,
    forwarded_sockets: Iterable[SocketPair] = (),
    options: dict[str, str] = SSH_DEFAULT_OPTIONS,
) -> SSHTunnel:
    """
    Build SSHTunnel for connecting to the container running the specified job.
    """
    jpd: JobProvisioningData = JobProvisioningData.__response__.parse_raw(
        job.job_provisioning_data
    )
    assert jpd.hostname is not None
    assert jpd.ssh_port is not None
    if not jpd.dockerized:
        ssh_destination = f"{jpd.username}@{jpd.hostname}"
        ssh_port = jpd.ssh_port
        ssh_proxy = jpd.ssh_proxy
    else:
        ssh_destination = "root@localhost"  # TODO(#1535): support non-root images properly
        ssh_port = DSTACK_RUNNER_SSH_PORT
        job_submission = jobs_services.job_model_to_job_submission(job)
        jrd = job_submission.job_runtime_data
        if jrd is not None and jrd.ports is not None:
            ssh_port = jrd.ports.get(ssh_port, ssh_port)
        ssh_proxy = SSHConnectionParams(
            hostname=jpd.hostname,
            username=jpd.username,
            port=jpd.ssh_port,
        )
        if jpd.backend == BackendType.LOCAL:
            ssh_proxy = None
    ssh_head_proxy: Optional[SSHConnectionParams] = None
    ssh_head_proxy_private_key: Optional[str] = None
    instance = get_or_error(job.instance)
    if instance.remote_connection_info is not None:
        rci = RemoteConnectionInfo.__response__.parse_raw(instance.remote_connection_info)
        if rci.ssh_proxy is not None:
            ssh_head_proxy = rci.ssh_proxy
            ssh_head_proxy_private_key = get_or_error(rci.ssh_proxy_keys)[0].private
    ssh_proxies = []
    if ssh_head_proxy is not None:
        ssh_head_proxy_private_key = get_or_error(ssh_head_proxy_private_key)
        ssh_proxies.append((ssh_head_proxy, FileContent(ssh_head_proxy_private_key)))
    if ssh_proxy is not None:
        ssh_proxies.append((ssh_proxy, None))
    return SSHTunnel(
        destination=ssh_destination,
        port=ssh_port,
        ssh_proxies=ssh_proxies,
        identity=FileContent(instance.project.ssh_private_key),
        forwarded_sockets=forwarded_sockets,
        options=options,
    )
