import json
from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.job import Job, JobStatus
from dstack._internal.core.run import RunHead
from dstack._internal.hub.db import reuse_or_make_session
from dstack._internal.hub.db.models import Job as DBJob


class JobManager:
    @staticmethod
    @reuse_or_make_session
    async def list_jobs(
        project_name: Optional[str] = None,
        status: Optional[JobStatus] = None,
        session: Optional[AsyncSession] = None,
    ) -> List[Job]:
        db_jobs = await JobManager._list_jobs(
            project_name=project_name, status=status, session=session
        )
        jobs = []
        for db_job in db_jobs:
            job = Job.unserialize(json.loads(db_job.job_data))
            job.status = db_job.status
            jobs.append(job)
        return jobs

    @staticmethod
    @reuse_or_make_session
    async def list_runs(
        project_name: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> List[RunHead]:
        jobs = await JobManager.list_jobs(
            project_name=project_name,
            session=session,
        )
        return [_job_to_run_head(job) for job in jobs]

    @staticmethod
    @reuse_or_make_session
    async def create(project_name: str, job: Job, session: Optional[AsyncSession] = None):
        db_job = DBJob(
            project_name=project_name,
            job_id=job.job_id,
            run_name=job.run_name,
            status=job.status.value,
            job_data=json.dumps(job.serialize()),
        )
        await JobManager._save(db_job, session=session)

    @staticmethod
    @reuse_or_make_session
    async def stop_jobs(project_name: str, run_name: str, session: Optional[AsyncSession] = None):
        await session.execute(
            update(DBJob)
            .where(
                DBJob.run_name == run_name,
                DBJob.project_name == project_name,
            )
            .values(
                status=JobStatus.ABORTED.value,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def delete_run_jobs(
        project_name: str, run_name: str, session: Optional[AsyncSession] = None
    ):
        await session.execute(
            delete(DBJob).where(
                DBJob.run_name == run_name,
                DBJob.project_name == project_name,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def delete_job(project_name: str, job_id: str, session: Optional[AsyncSession] = None):
        await session.execute(
            delete(DBJob).where(
                DBJob.job_id == job_id,
                DBJob.project_name == project_name,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def update(project_name: str, job: Job, session: Optional[AsyncSession] = None):
        db_job = DBJob(
            project_name=project_name,
            job_id=job.job_id,
            run_name=job.run_name,
            status=job.status.value,
            job_data=json.dumps(job.serialize()),
        )
        await JobManager._update(db_job, session=session)

    @staticmethod
    @reuse_or_make_session
    async def _list_jobs(
        project_name: Optional[str] = None,
        status: Optional[JobStatus] = None,
        session: Optional[AsyncSession] = None,
    ) -> List[DBJob]:
        filters = []
        if project_name is not None:
            filters.append(DBJob.project_name == project_name)
        if status is not None:
            filters.append(DBJob.status == status)
        query = await session.execute(select(DBJob).where(*filters))
        jobs = query.scalars().unique().all()
        return jobs

    @staticmethod
    @reuse_or_make_session
    async def _save(job: DBJob, session: Optional[AsyncSession] = None):
        session.add(job)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _update(job: DBJob, session: Optional[AsyncSession] = None):
        await session.execute(
            update(DBJob)
            .where(
                DBJob.job_id == job.job_id,
                DBJob.project_name == job.project_name,
            )
            .values(
                job_data=job.job_data,
                status=job.status,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _delete(job: DBJob, session: Optional[AsyncSession] = None):
        await session.delete(job)
        await session.commit()


def _job_to_run_head(
    job: Job,
) -> RunHead:
    return RunHead(
        run_name=job.run_name,
        configuration_path=job.configuration_path,
        hub_user_name=job.hub_user_name,
        status=job.status,
        job_heads=[job],
        submitted_at=job.submitted_at,
    )
