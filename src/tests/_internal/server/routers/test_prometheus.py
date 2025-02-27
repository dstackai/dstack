from textwrap import dedent

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.runs import JobStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import JobModel, ProjectModel, UserModel
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_job,
    create_job_prometheus_metrics,
    create_project,
    create_repo,
    create_run,
    create_user,
)


@pytest.fixture
def enable_metrics(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("dstack._internal.server.settings.ENABLE_PROMETHEUS_METRICS", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock", "test_db", "enable_metrics")
class TestGetPrometheusMetrics:
    async def test_returns_metrics(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project_2 = await _create_project(session, "project-2", user)
        job_2_1 = await _create_job(session, "run-1", project_2, user, JobStatus.RUNNING)
        await create_job_prometheus_metrics(
            session=session,
            job=job_2_1,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 100
                FIELD_1{gpu="1"} 200
            """),
        )
        project_1 = await _create_project(session, "project-1", user)
        job_1_1 = await _create_job(session, "run-1", project_1, user, JobStatus.RUNNING)
        await create_job_prometheus_metrics(
            session=session,
            job=job_1_1,
            text=dedent("""
                # Comments should be skipped

                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 350
                FIELD_1{gpu="1"} 400

                # HELP FIELD_2 Test field 2
                # TYPE FIELD_2 counter
                FIELD_2{gpu="0"} 337325 1395066363000
                FIELD_2{gpu="1"} 987169 1395066363010
            """),
        )
        job_1_2 = await _create_job(session, "run-2", project_1, user, JobStatus.RUNNING)
        await create_job_prometheus_metrics(
            session=session,
            job=job_1_2,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 1200.0
                FIELD_1{gpu="1"} 1600.0
                FIELD_1{gpu="2"} 2400.0
            """),
        )
        # Terminated job, should not appear in the response
        job_1_3 = await _create_job(session, "run-3", project_1, user, JobStatus.TERMINATED)
        await create_job_prometheus_metrics(
            session=session,
            job=job_1_3,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 10
                FIELD_1{gpu="1"} 20
            """),
        )

        response = await client.get("/metrics")

        assert response.status_code == 200
        assert response.text == dedent("""\
            # HELP FIELD_1 Test field 1
            # TYPE FIELD_1 gauge
            FIELD_1{gpu="0",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 350.0
            FIELD_1{gpu="1",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 400.0
            FIELD_1{gpu="0",dstack_project_name="project-1",dstack_run_name="run-2",dstack_job_name="run-2-0-0",dstack_job_num="0",dstack_replica_num="0"} 1200.0
            FIELD_1{gpu="1",dstack_project_name="project-1",dstack_run_name="run-2",dstack_job_name="run-2-0-0",dstack_job_num="0",dstack_replica_num="0"} 1600.0
            FIELD_1{gpu="2",dstack_project_name="project-1",dstack_run_name="run-2",dstack_job_name="run-2-0-0",dstack_job_num="0",dstack_replica_num="0"} 2400.0
            FIELD_1{gpu="0",dstack_project_name="project-2",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 100.0
            FIELD_1{gpu="1",dstack_project_name="project-2",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 200.0
            # HELP FIELD_2 Test field 2
            # TYPE FIELD_2 counter
            FIELD_2{gpu="0",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 337325.0 1395066363000
            FIELD_2{gpu="1",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 987169.0 1395066363010
        """)

    async def test_returns_empty_response_if_no_runs(self, client: AsyncClient):
        response = await client.get("/metrics")
        assert response.status_code == 200
        assert response.text == ""

    async def test_returns_404_if_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch, client: AsyncClient
    ):
        monkeypatch.setattr("dstack._internal.server.settings.ENABLE_PROMETHEUS_METRICS", False)
        response = await client.get("/metrics")
        assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
@pytest.mark.usefixtures("image_config_mock", "test_db", "enable_metrics")
class TestGetPrometheusProjectMetrics:
    async def test_returns_metrics(self, session: AsyncSession, client: AsyncClient):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await _create_project(session, "project-1", user)
        job_1 = await _create_job(session, "run-1", project, user, JobStatus.RUNNING)
        await create_job_prometheus_metrics(
            session=session,
            job=job_1,
            text=dedent("""
                # Comments should be skipped

                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 350
                FIELD_1{gpu="1"} 400

                # HELP FIELD_2 Test field 2
                # TYPE FIELD_2 counter
                FIELD_2{gpu="0"} 337325 1395066363000
                FIELD_2{gpu="1"} 987169 1395066363010
            """),
        )
        job_2 = await _create_job(session, "run-2", project, user, JobStatus.RUNNING)
        await create_job_prometheus_metrics(
            session=session,
            job=job_2,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 1200.0
                FIELD_1{gpu="1"} 1600.0
                FIELD_1{gpu="2"} 2400.0
            """),
        )
        # Terminated job, should not appear in the response
        job_3 = await _create_job(session, "run-3", project, user, JobStatus.TERMINATED)
        await create_job_prometheus_metrics(
            session=session,
            job=job_3,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 10
                FIELD_1{gpu="1"} 20
            """),
        )
        another_project = await _create_project(session, "project-2", user)
        another_project_job = await _create_job(
            session, "run-4", another_project, user, JobStatus.RUNNING
        )
        await create_job_prometheus_metrics(
            session=session,
            job=another_project_job,
            text=dedent("""
                # HELP FIELD_1 Test field 1
                # TYPE FIELD_1 gauge
                FIELD_1{gpu="0"} 100
                FIELD_1{gpu="1"} 200
            """),
        )

        response = await client.get("/metrics/project/project-1")

        assert response.status_code == 200
        assert response.text == dedent("""\
            # HELP FIELD_1 Test field 1
            # TYPE FIELD_1 gauge
            FIELD_1{gpu="0",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 350.0
            FIELD_1{gpu="1",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 400.0
            FIELD_1{gpu="0",dstack_project_name="project-1",dstack_run_name="run-2",dstack_job_name="run-2-0-0",dstack_job_num="0",dstack_replica_num="0"} 1200.0
            FIELD_1{gpu="1",dstack_project_name="project-1",dstack_run_name="run-2",dstack_job_name="run-2-0-0",dstack_job_num="0",dstack_replica_num="0"} 1600.0
            FIELD_1{gpu="2",dstack_project_name="project-1",dstack_run_name="run-2",dstack_job_name="run-2-0-0",dstack_job_num="0",dstack_replica_num="0"} 2400.0
            # HELP FIELD_2 Test field 2
            # TYPE FIELD_2 counter
            FIELD_2{gpu="0",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 337325.0 1395066363000
            FIELD_2{gpu="1",dstack_project_name="project-1",dstack_run_name="run-1",dstack_job_name="run-1-0-0",dstack_job_num="0",dstack_replica_num="0"} 987169.0 1395066363010
        """)

    async def test_returns_empty_response_if_no_runs(
        self, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session=session, global_role=GlobalRole.USER)
        await create_project(session=session, owner=user, name="test-project")
        response = await client.get("/metrics/project/test-project")
        assert response.status_code == 200
        assert response.text == ""

    async def test_returns_404_if_project_doesnt_exist(self, client: AsyncClient):
        response = await client.get("/metrics/project/nonexistent")
        assert response.status_code == 404

    async def test_returns_404_if_not_enabled(
        self, monkeypatch: pytest.MonkeyPatch, session: AsyncSession, client: AsyncClient
    ):
        monkeypatch.setattr("dstack._internal.server.settings.ENABLE_PROMETHEUS_METRICS", False)
        user = await create_user(session=session, global_role=GlobalRole.USER)
        await create_project(session=session, owner=user, name="test-project")
        response = await client.get("/metrics/project/test-project")
        assert response.status_code == 404


async def _create_project(session: AsyncSession, name: str, user: UserModel) -> ProjectModel:
    project = await create_project(session=session, owner=user, name=name)
    await add_project_member(
        session=session, project=project, user=user, project_role=ProjectRole.USER
    )
    return project


async def _create_job(
    session: AsyncSession, run_name: str, project: ProjectModel, user: UserModel, status: JobStatus
) -> JobModel:
    repo = await create_repo(session=session, project_id=project.id, repo_name=f"{run_name}-repo")
    run = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name=run_name,
    )
    job = await create_job(session=session, run=run, status=status)
    return job
