import re
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import Mock

import pytest
from rich.table import Table
from rich.text import Text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.cli.utils.run import get_runs_table
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.instances import Disk, InstanceType, Resources
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.runs import (
    JobProvisioningData,
    JobStatus,
    JobTerminationReason,
    RunStatus,
)
from dstack._internal.server.models import RunModel
from dstack._internal.server.services import encryption  # noqa: F401  # import for side-effect
from dstack._internal.server.services.runs import run_model_to_run
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_provisioning_data,
    get_run_spec,
)
from dstack.api import Run
from dstack.api.server import APIClient


def _strip_rich_markup(text: str) -> str:
    return re.sub(r"\[[^\]]*\]([^\[]*)\[/[^\]]*\]", r"\1", text)


def get_table_cells(table: Table) -> list[dict[str, str]]:
    rows = []

    if not table.columns:
        return rows

    num_rows = len(table.columns[0]._cells)

    for row_idx in range(num_rows):
        row = {}
        for col in table.columns:
            col_name = str(col.header)
            if row_idx < len(col._cells):
                cell_value = col._cells[row_idx]
                if isinstance(cell_value, Text):
                    row[col_name] = cell_value.plain
                else:
                    text = str(cell_value)
                    row[col_name] = _strip_rich_markup(text)
            else:
                row[col_name] = ""
        rows.append(row)

    return rows


def get_table_cell_style(table: Table, column_name: str, row_idx: int = 0) -> Optional[str]:
    for col in table.columns:
        if str(col.header) == column_name:
            if row_idx < len(col._cells):
                cell_value = col._cells[row_idx]
                if isinstance(cell_value, Text):
                    return str(cell_value.style) if cell_value.style else None
                text = str(cell_value)
                match = re.search(r"\[([^\]]+)\][^\[]*\[/\]", text)
                if match:
                    return match.group(1)
            return None
    return None


async def create_run_with_job(
    session: AsyncSession,
    run_name: str = "test-run",
    run_status: Optional[RunStatus] = None,
    job_status: JobStatus = JobStatus.RUNNING,
    configuration: Optional[AnyRunConfiguration] = None,
    job_provisioning_data: Optional[JobProvisioningData] = None,
    termination_reason: Optional[JobTerminationReason] = None,
    exit_status: Optional[int] = None,
    termination_reason_message: Optional[str] = None,
    submitted_at: Optional[datetime] = None,
) -> Run:
    if submitted_at is None:
        submitted_at = datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    project = await create_project(session=session)
    user = await create_user(session=session)
    repo = await create_repo(session=session, project_id=project.id)

    if configuration is None:
        configuration = TaskConfiguration(
            type="task",
            image="ubuntu:latest",
            commands=["echo hello"],
        )

    if run_status is None:
        if job_status == JobStatus.DONE:
            run_status = RunStatus.DONE
        elif job_status == JobStatus.FAILED:
            run_status = RunStatus.FAILED
        elif job_status in [JobStatus.TERMINATED, JobStatus.ABORTED]:
            run_status = RunStatus.TERMINATED
        elif job_status == JobStatus.TERMINATING:
            run_status = RunStatus.TERMINATING
        elif job_status == JobStatus.PROVISIONING:
            run_status = RunStatus.PROVISIONING
        elif job_status == JobStatus.PULLING:
            run_status = RunStatus.PROVISIONING
        else:
            run_status = RunStatus.RUNNING

    run_spec = get_run_spec(
        run_name=run_name,
        repo_id=repo.name,
        profile=Profile(name="default"),
        configuration=configuration,
    )

    run_model_db = await create_run(
        session=session,
        project=project,
        repo=repo,
        user=user,
        run_name=run_name,
        run_spec=run_spec,
        status=run_status,
        submitted_at=submitted_at,
    )

    if job_provisioning_data is None:
        resources = Resources(
            cpus=2,
            memory_mib=4096,
            gpus=[],
            spot=False,
            disk=Disk(size_mib=102400),
        )
        instance_type = InstanceType(name="t2.medium", resources=resources)
        job_provisioning_data = get_job_provisioning_data(
            backend=BackendType.AWS,
            region="us-east-1",
            cpu_count=2,
            memory_gib=4,
            spot=False,
            hostname="1.2.3.4",
            price=0.0464,
            instance_type=instance_type,
        )

    job_model = await create_job(
        session=session,
        run=run_model_db,
        status=job_status,
        submitted_at=submitted_at,
        last_processed_at=submitted_at,
        job_provisioning_data=job_provisioning_data,
        termination_reason=termination_reason,
    )

    if exit_status is not None:
        job_model.exit_status = exit_status
    if termination_reason_message is not None:
        job_model.termination_reason_message = termination_reason_message
    if exit_status is not None or termination_reason_message is not None:
        await session.commit()

    await session.refresh(run_model_db)

    res = await session.execute(
        select(RunModel).where(RunModel.id == run_model_db.id).options(selectinload(RunModel.jobs))
    )
    run_model_db = res.scalar_one()

    run_model = run_model_to_run(run_model_db)

    return Run(
        api_client=Mock(spec=APIClient),
        project=project.name,
        run=run_model,
    )


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("test_db", "image_config_mock"),
    pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True),
]


class TestGetRunsTable:
    async def test_simple_run(self, session: AsyncSession):
        api_run = await create_run_with_job(session=session)
        table = get_runs_table([api_run], verbose=False)

        cells = get_table_cells(table)
        assert len(cells) == 1
        row = cells[0]

        assert row["NAME"] == "test-run"
        assert row["BACKEND"] == "aws (us-east-1)"
        assert row["GPU"] == "-"
        assert row["PRICE"] == "$0.0464"
        assert row["STATUS"] == "running"
        assert row["SUBMITTED"] == "3 years ago"

        name_column = next(col for col in table.columns if str(col.header) == "NAME")
        assert name_column.style == "bold"

        status_style = get_table_cell_style(table, "STATUS", 0)
        assert status_style == "bold sea_green3"

    @pytest.mark.parametrize(
        "job_status,termination_reason,exit_status,termination_reason_message,expected_status,expected_style",
        [
            (JobStatus.DONE, None, None, None, "exited (0)", "grey"),
            (
                JobStatus.FAILED,
                JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
                1,
                None,
                "exited (1)",
                "indian_red1",
            ),
            (
                JobStatus.FAILED,
                JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
                42,
                None,
                "exited (42)",
                "indian_red1",
            ),
            (
                JobStatus.FAILED,
                JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
                None,
                None,
                "no offers",
                "gold1",
            ),
            (
                JobStatus.FAILED,
                JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
                None,
                "No matching fleet found. Possible reasons: https://dstack.ai/docs/guides/troubleshooting/#no-fleets",
                "no fleets",
                "indian_red1",
            ),
            (
                JobStatus.FAILED,
                JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
                None,
                None,
                "interrupted",
                "gold1",
            ),
            (
                JobStatus.FAILED,
                JobTerminationReason.INSTANCE_UNREACHABLE,
                None,
                None,
                "error",
                "indian_red1",
            ),
            (
                JobStatus.TERMINATED,
                JobTerminationReason.TERMINATED_BY_USER,
                None,
                None,
                "stopped",
                "grey",
            ),
            (
                JobStatus.TERMINATED,
                JobTerminationReason.ABORTED_BY_USER,
                None,
                None,
                "aborted",
                "grey",
            ),
            (JobStatus.RUNNING, None, None, None, "running", "bold sea_green3"),
            (JobStatus.PROVISIONING, None, None, None, "provisioning", "bold deep_sky_blue1"),
            (JobStatus.PULLING, None, None, None, "pulling", "bold sea_green3"),
            (JobStatus.TERMINATING, None, None, None, "terminating", "bold deep_sky_blue1"),
        ],
    )
    async def test_status_messages(
        self,
        session: AsyncSession,
        job_status: JobStatus,
        termination_reason: Optional[JobTerminationReason],
        exit_status: Optional[int],
        termination_reason_message: Optional[str],
        expected_status: str,
        expected_style: str,
    ):
        api_run = await create_run_with_job(
            session=session,
            job_status=job_status,
            termination_reason=termination_reason,
            exit_status=exit_status,
            termination_reason_message=termination_reason_message,
        )

        table = get_runs_table([api_run], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 1
        assert cells[0]["STATUS"] == expected_status

        status_style = get_table_cell_style(table, "STATUS", 0)
        assert status_style == expected_style

    async def test_multi_node_task_with_multiple_jobs(self, session: AsyncSession):
        # Verifies that a multi-node task with 3 jobs (all same replica_num=0, different job_num=0,1,2)
        # displays only job= in table rows, not replica=, since all jobs share the same replica.
        # Expected: 4 rows total (1 run header + 3 job rows with job=0,1,2).
        submitted_at = datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)

        configuration = TaskConfiguration(
            type="task",
            image="ubuntu:latest",
            commands=["echo hello"],
            nodes=3,
        )

        run_spec = get_run_spec(
            run_name="multi-node-run",
            repo_id=repo.name,
            profile=Profile(name="default"),
            configuration=configuration,
        )

        run_model_db = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="multi-node-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            submitted_at=submitted_at,
        )

        resources = Resources(
            cpus=2,
            memory_mib=4096,
            gpus=[],
            spot=False,
            disk=Disk(size_mib=102400),
        )
        instance_type = InstanceType(name="t2.medium", resources=resources)
        job_provisioning_data = get_job_provisioning_data(
            backend=BackendType.AWS,
            region="us-east-1",
            cpu_count=2,
            memory_gib=4,
            spot=False,
            hostname="1.2.3.4",
            price=0.0464,
            instance_type=instance_type,
        )

        for job_num in range(3):
            await create_job(
                session=session,
                run=run_model_db,
                status=JobStatus.RUNNING,
                submitted_at=submitted_at,
                last_processed_at=submitted_at,
                job_provisioning_data=job_provisioning_data,
                replica_num=0,
                job_num=job_num,
            )

        await session.refresh(run_model_db)

        res = await session.execute(
            select(RunModel)
            .where(RunModel.id == run_model_db.id)
            .options(selectinload(RunModel.jobs))
        )
        run_model_db = res.scalar_one()

        run_model = run_model_to_run(run_model_db)

        api_run = Run(
            api_client=Mock(spec=APIClient),
            project=project.name,
            run=run_model,
        )

        table = get_runs_table([api_run], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 4
        assert cells[0]["NAME"] == "multi-node-run"

        for i in range(1, 4):
            job_row = cells[i]
            assert "replica=" not in job_row["NAME"]
            assert f"job={i - 1}" in job_row["NAME"]
            assert job_row["STATUS"] == "running"

    async def test_service_with_multiple_replicas_and_jobs(self, session: AsyncSession):
        # Verifies that a service with 3 replicas and 1 job per replica displays replica= but not job=
        # in table rows (since there's only one job per replica). Expected: 4 rows total (1 run header + 3 job rows).
        submitted_at = datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)

        configuration = ServiceConfiguration(
            type="service",
            image="ubuntu:latest",
            commands=["echo hello"],
            port=8000,
            replicas=Range[int](min=3, max=3),
        )

        run_spec = get_run_spec(
            run_name="service-run",
            repo_id=repo.name,
            profile=Profile(name="default"),
            configuration=configuration,
        )

        run_model_db = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="service-run",
            run_spec=run_spec,
            status=RunStatus.RUNNING,
            submitted_at=submitted_at,
        )

        resources = Resources(
            cpus=2,
            memory_mib=4096,
            gpus=[],
            spot=False,
            disk=Disk(size_mib=102400),
        )
        instance_type = InstanceType(name="t2.medium", resources=resources)
        job_provisioning_data = get_job_provisioning_data(
            backend=BackendType.AWS,
            region="us-east-1",
            cpu_count=2,
            memory_gib=4,
            spot=False,
            hostname="1.2.3.4",
            price=0.0464,
            instance_type=instance_type,
        )

        for replica_num in range(3):
            await create_job(
                session=session,
                run=run_model_db,
                status=JobStatus.RUNNING,
                submitted_at=submitted_at,
                last_processed_at=submitted_at,
                job_provisioning_data=job_provisioning_data,
                replica_num=replica_num,
                job_num=0,
            )

        await session.refresh(run_model_db)

        res = await session.execute(
            select(RunModel)
            .where(RunModel.id == run_model_db.id)
            .options(selectinload(RunModel.jobs))
        )
        run_model_db = res.scalar_one()

        run_model = run_model_to_run(run_model_db)

        api_run = Run(
            api_client=Mock(spec=APIClient),
            project=project.name,
            run=run_model,
        )

        table = get_runs_table([api_run], verbose=False)
        cells = get_table_cells(table)

        assert len(cells) == 4
        assert cells[0]["NAME"] == "service-run"

        for i in range(1, 4):
            job_row = cells[i]
            assert f"replica={i - 1}" in job_row["NAME"]
            assert "job=" not in job_row["NAME"]
            assert job_row["STATUS"] == "running"
