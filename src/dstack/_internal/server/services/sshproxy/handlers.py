from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.server.models import (
    InstanceModel,
    JobModel,
    ProjectModel,
    RunModel,
    UserModel,
)
from dstack._internal.server.schemas.sshproxy import GetUpstreamResponse, UpstreamHost
from dstack._internal.server.services.jobs import get_job_runtime_data, get_job_spec
from dstack._internal.server.services.runs import get_run_spec
from dstack._internal.server.services.ssh import get_container_ssh_credentials


async def get_upstream_response(
    session: AsyncSession,
    upstream_id: str,
) -> Optional[GetUpstreamResponse]:
    # The format of upstream_id is intentionally not limited to UUID in the API schema to allow
    # further extensions. Currently, it's just a JobModel.id
    try:
        job_id = UUID(upstream_id)
    except ValueError:
        return None

    res = await session.execute(
        select(JobModel)
        .where(
            JobModel.id == job_id,
            JobModel.status == JobStatus.RUNNING,
        )
        .options(
            joinedload(JobModel.project, innerjoin=True).load_only(ProjectModel.ssh_private_key),
            (
                joinedload(JobModel.instance, innerjoin=True)
                .load_only(InstanceModel.remote_connection_info)
                .joinedload(InstanceModel.project, innerjoin=True)
                .load_only(ProjectModel.ssh_private_key)
            ),
            (
                joinedload(JobModel.run, innerjoin=True)
                .load_only(RunModel.run_spec)
                .joinedload(RunModel.user, innerjoin=True)
                .load_only(UserModel.ssh_public_key)
            ),
        )
    )
    job = res.scalar_one_or_none()
    if job is None:
        return None

    hosts: list[UpstreamHost] = []
    for ssh_params, private_key in get_container_ssh_credentials(job):
        hosts.append(
            UpstreamHost(
                host=ssh_params.hostname,
                port=ssh_params.port,
                user=ssh_params.username,
                private_key=private_key.content,
            )
        )

    username: Optional[str] = None
    if (jrd := get_job_runtime_data(job)) is not None:
        username = jrd.username
    if username is None and (job_spec_user := get_job_spec(job).user) is not None:
        username = job_spec_user.username
    if username is not None:
        hosts[-1].user = username

    authorized_keys: set[str] = set()
    if (run_spec_key := get_run_spec(job.run).ssh_key_pub) is not None:
        authorized_keys.add(run_spec_key)
    if (user_key := job.run.user.ssh_public_key) is not None:
        authorized_keys.add(user_key)

    return GetUpstreamResponse(
        hosts=hosts,
        authorized_keys=list(authorized_keys),
    )
