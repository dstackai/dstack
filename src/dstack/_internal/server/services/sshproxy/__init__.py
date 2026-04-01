from typing import Optional

from dstack._internal.server import settings
from dstack._internal.server.models import JobModel
from dstack._internal.utils.ssh import build_ssh_command, build_ssh_url_authority


def build_proxied_job_ssh_url_authority(job: JobModel) -> Optional[str]:
    if not settings.SSHPROXY_ENABLED:
        return None
    assert settings.SSHPROXY_HOSTNAME is not None
    return build_ssh_url_authority(
        username=build_proxied_job_upstream_id(job),
        hostname=settings.SSHPROXY_HOSTNAME,
        port=settings.SSHPROXY_PORT,
    )


def build_proxied_job_ssh_command(job: JobModel) -> Optional[list[str]]:
    if not settings.SSHPROXY_ENABLED:
        return None
    assert settings.SSHPROXY_HOSTNAME is not None
    return build_ssh_command(
        username=build_proxied_job_upstream_id(job),
        hostname=settings.SSHPROXY_HOSTNAME,
        port=settings.SSHPROXY_PORT,
    )


def build_proxied_job_upstream_id(job: JobModel) -> str:
    # Job's UUID in lowercase, without dashes
    return job.id.hex
