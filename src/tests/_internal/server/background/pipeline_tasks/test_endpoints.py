import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoints import EndpointConfiguration, EndpointStatus
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.runs import JobStatus, RunSpec, RunStatus, ServiceSpec
from dstack._internal.server.background.pipeline_tasks.endpoints import (
    EndpointPipelineItem,
    EndpointWorker,
)
from dstack._internal.server.db import get_session_ctx
from dstack._internal.server.models import EndpointModel, EndpointRunSubmissionModel, RunModel
from dstack._internal.server.services.endpoints import record_endpoint_run_submission
from dstack._internal.server.services.endpoints.agent import AgentPlan, AgentProvisioningResult
from dstack._internal.server.services.endpoints.agent.report import AgentFinalReport
from dstack._internal.server.services.endpoints.names import get_endpoint_serving_run_name
from dstack._internal.server.services.endpoints.planning import EndpointPresetPlanningResult
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    list_events,
)


@pytest.fixture
def worker() -> EndpointWorker:
    return EndpointWorker(queue=Mock(), heartbeater=Mock(), pipeline_hinter=Mock())


class _FakeAgentService:
    def __init__(self, result: AgentProvisioningResult | None = None, side_effect=None):
        self.provision_endpoint = AsyncMock(
            return_value=result or AgentProvisioningResult(),
            side_effect=side_effect,
        )

    def is_enabled(self) -> bool:
        return True

    def get_plan(self) -> AgentPlan:
        return AgentPlan(model="test-agent")


def _endpoint_to_pipeline_item(endpoint_model: EndpointModel) -> EndpointPipelineItem:
    assert endpoint_model.lock_token is not None
    assert endpoint_model.lock_expires_at is not None
    return EndpointPipelineItem(
        __tablename__=endpoint_model.__tablename__,
        id=endpoint_model.id,
        lock_token=endpoint_model.lock_token,
        lock_expires_at=endpoint_model.lock_expires_at,
        prev_lock_expired=False,
        status=endpoint_model.status,
        to_be_deleted=endpoint_model.to_be_deleted,
    )


async def _lock_endpoint_model(session: AsyncSession, endpoint_model: EndpointModel) -> None:
    endpoint_model.lock_token = uuid.uuid4()
    endpoint_model.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
    await session.commit()


async def _create_endpoint_model(
    session: AsyncSession,
    status: EndpointStatus = EndpointStatus.SUBMITTED,
    to_be_deleted: bool = False,
    user_ssh_public_key: str | None = None,
) -> EndpointModel:
    project = await create_project(session=session)
    user = await create_user(session=session, ssh_public_key=user_ssh_public_key)
    configuration = EndpointConfiguration(
        name="qwen-endpoint",
        model="Qwen/Qwen3-0.6B",
        env=Env.parse_obj({"HF_TOKEN": "secret"}),
    )
    endpoint_model = EndpointModel(
        project=project,
        user=user,
        name=configuration.name,
        status=status,
        configuration=configuration.json(),
        created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        last_processed_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        to_be_deleted=to_be_deleted,
    )
    endpoint_model.lock_token = uuid.uuid4()
    endpoint_model.lock_expires_at = datetime(2025, 1, 2, 3, 4, tzinfo=timezone.utc)
    session.add(endpoint_model)
    await session.commit()
    return endpoint_model


async def _create_backing_service_run(
    session: AsyncSession,
    endpoint_model: EndpointModel,
    status: RunStatus = RunStatus.RUNNING,
    job_status: JobStatus = JobStatus.RUNNING,
    registered: bool = True,
    deleted: bool = False,
    service_model_base_url: str | None = "/proxy/services/main/qwen-endpoint-serving/v1",
    link_endpoint: bool = True,
    run_name: str | None = None,
):
    if run_name is None:
        run_name = get_endpoint_serving_run_name(endpoint_model.name)
    assert run_name is not None
    repo = await create_repo(
        session=session,
        project_id=endpoint_model.project_id,
        repo_name=f"{run_name}-repo",
    )
    run_spec = RunSpec(
        run_name=run_name,
        configuration=ServiceConfiguration.parse_obj(
            {
                "type": "service",
                "name": run_name,
                "commands": [
                    "vllm serve Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000",
                ],
                "port": 8000,
                "model": "Qwen/Qwen3-0.6B",
                "resources": {"gpu": "16GB"},
            }
        ),
    )
    run = await create_run(
        session=session,
        project=endpoint_model.project,
        repo=repo,
        user=endpoint_model.user,
        run_name=run_name,
        status=status,
        run_spec=run_spec,
        deleted=deleted,
    )
    if service_model_base_url is not None:
        run.service_spec = ServiceSpec.parse_obj(
            {
                "url": "/proxy/services/main/qwen-endpoint-serving/",
                "model": {
                    "name": "Qwen/Qwen3-0.6B",
                    "base_url": service_model_base_url,
                    "type": "chat",
                },
            }
        ).json()
    if link_endpoint:
        endpoint_model.service_run_id = run.id
    await create_job(
        session=session,
        run=run,
        status=job_status,
        registered=registered,
    )
    await session.commit()
    return run


async def _create_ready_backing_service_run_for_agent(
    endpoint_id: uuid.UUID,
) -> AgentProvisioningResult:
    async with get_session_ctx() as session:
        res = await session.execute(
            select(EndpointModel)
            .where(EndpointModel.id == endpoint_id)
            .options(joinedload(EndpointModel.project))
            .options(joinedload(EndpointModel.user))
        )
        endpoint_model = res.unique().scalar_one()
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            link_endpoint=False,
            run_name=_get_agent_run_name(),
        )
        return _get_verified_agent_result(run)


def _get_verified_agent_result(
    run: RunModel,
    *,
    run_id: uuid.UUID | None = None,
    run_name: str | None = None,
) -> AgentProvisioningResult:
    return AgentProvisioningResult(
        run_id=run_id if run_id is not None else run.id,
        run_name=run_name if run_name is not None else run.run_name,
        final_report=AgentFinalReport(
            success=True,
            run_id=run.id,
            run_name=run.run_name,
            service_yaml=f"type: service\nname: {run.run_name}\n",
            verification_summary="Agent verified the model endpoint.",
        ),
    )


def _get_agent_run_name(suffix: str = "candidate") -> str:
    return f"agent-{suffix}"


async def _get_endpoint_run_submissions(
    session: AsyncSession,
    endpoint_model: EndpointModel,
) -> list[EndpointRunSubmissionModel]:
    res = await session.execute(
        select(EndpointRunSubmissionModel)
        .where(EndpointRunSubmissionModel.endpoint_id == endpoint_model.id)
        .order_by(EndpointRunSubmissionModel.submission_num)
    )
    return list(res.scalars().all())


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestRecordEndpointRunSubmission:
    async def test_records_ordered_submissions_and_is_idempotent(
        self, test_db, session: AsyncSession
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        repo = await create_repo(
            session=session,
            project_id=endpoint_model.project_id,
            repo_name="submissions-repo",
        )
        run_1 = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=endpoint_model.user,
            run_name="qwen-endpoint-1",
        )
        run_2 = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=endpoint_model.user,
            run_name="qwen-endpoint-2",
        )

        submission_1 = await record_endpoint_run_submission(
            session=session,
            endpoint_id=endpoint_model.id,
            run_id=run_1.id,
        )
        duplicate_submission_1 = await record_endpoint_run_submission(
            session=session,
            endpoint_id=endpoint_model.id,
            run_id=run_1.id,
        )
        submission_2 = await record_endpoint_run_submission(
            session=session,
            endpoint_id=endpoint_model.id,
            run_id=run_2.id,
        )
        await session.commit()

        assert duplicate_submission_1 is submission_1
        assert submission_1.submission_num == 1
        assert submission_2.submission_num == 2
        submissions = await _get_endpoint_run_submissions(
            session=session,
            endpoint_model=endpoint_model,
        )
        assert [submission.run_id for submission in submissions] == [run_1.id, run_2.id]
        assert [submission.submission_num for submission in submissions] == [1, 2]

    async def test_rejects_run_already_recorded_for_another_endpoint(
        self, test_db, session: AsyncSession
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        other_configuration = EndpointConfiguration(
            name="other-qwen-endpoint",
            model="Qwen/Qwen3-0.6B",
            env=Env.parse_obj({"HF_TOKEN": "secret"}),
        )
        other_endpoint_model = EndpointModel(
            project=endpoint_model.project,
            user=endpoint_model.user,
            name=other_configuration.name,
            status=EndpointStatus.SUBMITTED,
            configuration=other_configuration.json(),
            created_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
            last_processed_at=datetime(2023, 1, 2, 3, 5, tzinfo=timezone.utc),
        )
        session.add(other_endpoint_model)
        await session.commit()
        repo = await create_repo(
            session=session,
            project_id=endpoint_model.project_id,
            repo_name="recorded-run-repo",
        )
        run = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=endpoint_model.user,
            run_name="recorded-run",
        )
        await record_endpoint_run_submission(
            session=session,
            endpoint_id=endpoint_model.id,
            run_id=run.id,
        )
        await session.commit()

        with pytest.raises(ServerClientError, match="Run is already recorded"):
            await record_endpoint_run_submission(
                session=session,
                endpoint_id=other_endpoint_model.id,
                run_id=run.id,
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestEndpointWorkerSubmitted:
    async def test_fails_when_same_name_run_exists_without_link(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.PROVISIONING,
            link_endpoint=False,
        )

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(),
            ) as find_preset_planning_result_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.runs_services.apply_plan",
                new=AsyncMock(),
            ) as apply_plan_mock,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == (
            "Run name 'qwen-endpoint-serving' is taken by an existing run"
        )
        assert endpoint_model.service_run_id is None
        assert run.status == RunStatus.PROVISIONING
        assert run.deleted is False
        find_preset_planning_result_mock.assert_not_awaited()
        apply_plan_mock.assert_not_awaited()
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Endpoint status changed SUBMITTED -> FAILED "
            "(Run name 'qwen-endpoint-serving' is taken by an existing run)"
        )

    async def test_fails_when_run_name_is_taken_by_another_user(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        repo = await create_repo(session=session, project_id=endpoint_model.project_id)
        another_user = await create_user(session=session, name="another-user")
        run = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=another_user,
            run_name=get_endpoint_serving_run_name(endpoint_model.name),
            status=RunStatus.RUNNING,
        )

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(),
            ) as find_preset_planning_result_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.runs_services.apply_plan",
                new=AsyncMock(),
            ) as apply_plan_mock,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == (
            "Run name 'qwen-endpoint-serving' is taken by an existing run"
        )
        assert endpoint_model.service_run_id is None
        assert run.status == RunStatus.RUNNING
        assert run.deleted is False
        find_preset_planning_result_mock.assert_not_awaited()
        apply_plan_mock.assert_not_awaited()
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Endpoint status changed SUBMITTED -> FAILED "
            "(Run name 'qwen-endpoint-serving' is taken by an existing run)"
        )

    async def test_fails_when_run_name_is_taken_by_pre_existing_run(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        repo = await create_repo(session=session, project_id=endpoint_model.project_id)
        run = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=endpoint_model.user,
            run_name=get_endpoint_serving_run_name(endpoint_model.name),
            status=RunStatus.RUNNING,
            submitted_at=datetime(2023, 1, 2, 3, 3, tzinfo=timezone.utc),
        )

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints."
            "find_preset_planning_result",
            new=AsyncMock(),
        ) as find_preset_planning_result_mock:
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == (
            "Run name 'qwen-endpoint-serving' is taken by an existing run"
        )
        assert endpoint_model.service_run_id is None
        assert run.status == RunStatus.RUNNING
        assert run.deleted is False
        find_preset_planning_result_mock.assert_not_awaited()

    async def test_finished_same_name_run_does_not_block_preset_submission(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            user_ssh_public_key="ssh-rsa test",
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.DONE,
            link_endpoint=False,
        )
        preset_plan = Mock()
        preset_plan.preset.name = "qwen"
        preset_plan.run_plan.run_spec = RunSpec(
            run_name="qwen-endpoint-serving",
            configuration=ServiceConfiguration.parse_obj(
                {
                    "type": "service",
                    "name": "qwen-endpoint-serving",
                    "commands": [
                        "vllm serve Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000",
                    ],
                    "port": 8000,
                    "model": "Qwen/Qwen3-0.6B",
                    "resources": {"gpu": "16GB"},
                }
            ),
        )
        preset_plan.run_plan.current_resource = None

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(
                    return_value=EndpointPresetPlanningResult(provisionable=preset_plan)
                ),
            ) as find_preset_planning_result_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.runs_services.apply_plan",
                new=AsyncMock(return_value=Mock(id=run.id)),
            ) as apply_plan_mock,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.PROVISIONING
        assert endpoint_model.status_message is None
        assert endpoint_model.provisioning_method == "preset:qwen"
        assert run.status == RunStatus.DONE
        assert run.deleted is False
        find_preset_planning_result_mock.assert_awaited_once()
        apply_plan_mock.assert_awaited_once()

    async def test_submitted_to_failed_without_provisioning_path(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(session=session)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints."
            "find_preset_planning_result",
            new=AsyncMock(return_value=EndpointPresetPlanningResult()),
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert (
            endpoint_model.status_message == "No matching endpoint presets found. "
            "Creating a preset requires the server agent, but "
            "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
        )
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Endpoint status changed SUBMITTED -> FAILED "
            "(No matching endpoint presets found. "
            "Creating a preset requires the server agent, but "
            "DSTACK_AGENT_ANTHROPIC_API_KEY is not set.)"
        )

    async def test_submitted_to_agenting_with_agent(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        agent_service = _FakeAgentService()

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(return_value=EndpointPresetPlanningResult()),
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
                return_value=agent_service,
            ),
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.AGENTING
        assert endpoint_model.status_message is None
        assert endpoint_model.service_run_id is None
        assert endpoint_model.provisioning_method == "agent"
        agent_service.provision_endpoint.assert_not_awaited()
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint status changed SUBMITTED -> AGENTING"

    async def test_submitted_to_provisioning_with_matching_preset(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            user_ssh_public_key="ssh-rsa test",
        )
        repo = await create_repo(session=session, project_id=endpoint_model.project_id)
        run = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=endpoint_model.user,
            run_name="qwen-endpoint-submitted",
        )
        preset_plan = Mock()
        preset_plan.preset.name = "qwen"
        preset_plan.run_plan.run_spec = RunSpec(
            run_name="qwen-endpoint-serving",
            configuration=ServiceConfiguration.parse_obj(
                {
                    "type": "service",
                    "name": "qwen-endpoint-serving",
                    "commands": [
                        "vllm serve Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000",
                    ],
                    "port": 8000,
                    "model": "Qwen/Qwen3-0.6B",
                    "resources": {"gpu": "16GB"},
                }
            ),
        )
        preset_plan.run_plan.current_resource = None

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(
                    return_value=EndpointPresetPlanningResult(provisionable=preset_plan)
                ),
            ) as find_preset_planning_result_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.runs_services.apply_plan",
                new=AsyncMock(return_value=Mock(id=run.id)),
            ) as apply_plan_mock,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.PROVISIONING
        assert endpoint_model.status_message is None
        assert endpoint_model.service_run_id == run.id
        assert endpoint_model.provisioning_method == "preset:qwen"
        submissions = await _get_endpoint_run_submissions(
            session=session,
            endpoint_model=endpoint_model,
        )
        assert len(submissions) == 1
        assert submissions[0].run_id == run.id
        assert submissions[0].submission_num == 1
        find_preset_planning_result_mock.assert_awaited_once()
        apply_plan_mock.assert_awaited_once()
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint status changed SUBMITTED -> PROVISIONING"

    async def test_submitted_to_failed_when_preset_submission_fails(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            user_ssh_public_key="ssh-rsa test",
        )
        preset_plan = Mock()
        preset_plan.preset.name = "qwen"
        preset_plan.run_plan.run_spec = RunSpec(
            run_name="qwen-endpoint-serving",
            configuration=ServiceConfiguration.parse_obj(
                {
                    "type": "service",
                    "name": "qwen-endpoint-serving",
                    "commands": [
                        "vllm serve Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000",
                    ],
                    "port": 8000,
                    "model": "Qwen/Qwen3-0.6B",
                    "resources": {"gpu": "16GB"},
                }
            ),
        )
        preset_plan.run_plan.current_resource = None

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(
                    return_value=EndpointPresetPlanningResult(provisionable=preset_plan)
                ),
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.runs_services.apply_plan",
                new=AsyncMock(side_effect=ServerClientError("Cannot override active run")),
            ) as apply_plan_mock,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "Cannot override active run"
        apply_plan_mock.assert_awaited_once()
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message
            == "Endpoint status changed SUBMITTED -> FAILED (Cannot override active run)"
        )

    async def test_delete_request_after_fetch_prevents_preset_submission(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            user_ssh_public_key="ssh-rsa test",
        )
        item = _endpoint_to_pipeline_item(endpoint_model)
        endpoint_model.to_be_deleted = True
        await session.commit()

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(),
            ) as find_preset_planning_result_mock,
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.runs_services.apply_plan",
                new=AsyncMock(),
            ) as apply_plan_mock,
        ):
            await worker.process(item)

        await session.refresh(endpoint_model)
        assert endpoint_model.deleted is True
        assert endpoint_model.deleted_at is not None
        find_preset_planning_result_mock.assert_not_awaited()
        apply_plan_mock.assert_not_awaited()
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint deleted"


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestEndpointWorkerProvisioning:
    async def test_agenting_does_not_fail_on_legacy_same_name_run_conflict(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        legacy_run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.PROVISIONING,
            link_endpoint=False,
        )
        agent_run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            link_endpoint=False,
            run_name=_get_agent_run_name(),
        )
        agent_service = _FakeAgentService(result=_get_verified_agent_result(agent_run))

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(legacy_run)
        await session.refresh(agent_run)
        assert endpoint_model.status == EndpointStatus.PROVISIONING
        assert endpoint_model.status_message is None
        assert endpoint_model.service_run_id == agent_run.id
        assert legacy_run.status == RunStatus.PROVISIONING
        assert legacy_run.deleted is False
        assert agent_run.deleted is False
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint status changed AGENTING -> PROVISIONING"

    async def test_fails_when_agent_reports_foreign_run(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        repo = await create_repo(session=session, project_id=endpoint_model.project_id)
        another_user = await create_user(session=session, name="another-user")
        run = await create_run(
            session=session,
            project=endpoint_model.project,
            repo=repo,
            user=another_user,
            run_name=_get_agent_run_name(),
            status=RunStatus.RUNNING,
        )
        agent_service = _FakeAgentService(result=_get_verified_agent_result(run))

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == (
            "Run 'agent-candidate' is not owned by the endpoint user"
        )
        assert endpoint_model.service_run_id is None
        assert run.status == RunStatus.RUNNING
        assert run.deleted is False
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Endpoint status changed AGENTING -> FAILED "
            "(Run 'agent-candidate' is not owned by the endpoint user)"
        )

    async def test_agent_creates_ready_service_and_endpoint_becomes_running(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(session=session)
        preset_service = Mock()
        preset_service.save_preset = AsyncMock(side_effect=lambda preset, comments: preset)

        async def provision_endpoint(endpoint_model, pipeline_hinter):
            return await _create_ready_backing_service_run_for_agent(endpoint_model.id)

        agent_service = _FakeAgentService(side_effect=provision_endpoint)

        with (
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "find_preset_planning_result",
                new=AsyncMock(return_value=EndpointPresetPlanningResult()),
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
                return_value=agent_service,
            ),
            patch(
                "dstack._internal.server.background.pipeline_tasks.endpoints."
                "get_endpoint_preset_service",
                return_value=preset_service,
            ),
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))
            await session.refresh(endpoint_model)
            assert endpoint_model.status == EndpointStatus.AGENTING
            await _lock_endpoint_model(session=session, endpoint_model=endpoint_model)

            await worker.process(_endpoint_to_pipeline_item(endpoint_model))
            await session.refresh(endpoint_model)
            assert endpoint_model.status == EndpointStatus.PROVISIONING
            assert endpoint_model.service_run_id is not None
            await _lock_endpoint_model(session=session, endpoint_model=endpoint_model)

            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.RUNNING
        assert endpoint_model.status_message is None
        submissions = await _get_endpoint_run_submissions(
            session=session,
            endpoint_model=endpoint_model,
        )
        assert len(submissions) == 1
        assert submissions[0].run_id == endpoint_model.service_run_id
        assert submissions[0].submission_num == 1
        agent_service.provision_endpoint.assert_awaited_once()
        preset_service.save_preset.assert_awaited_once()

    async def test_agent_reported_run_id_links_backing_service_run(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        endpoint_model.provisioning_method = "agent"
        await session.commit()

        async def provision_endpoint(endpoint_model, pipeline_hinter):
            async with get_session_ctx() as provisioning_session:
                res = await provisioning_session.execute(
                    select(EndpointModel)
                    .where(EndpointModel.id == endpoint_model.id)
                    .options(joinedload(EndpointModel.project))
                    .options(joinedload(EndpointModel.user))
                )
                provisioning_endpoint = res.unique().scalar_one()
                run = await _create_backing_service_run(
                    session=provisioning_session,
                    endpoint_model=provisioning_endpoint,
                    link_endpoint=False,
                    run_name=_get_agent_run_name(),
                )
                return AgentProvisioningResult(
                    run_id=run.id,
                    final_report=AgentFinalReport(
                        success=True,
                        run_id=run.id,
                        run_name=run.run_name,
                        service_yaml=f"type: service\nname: {run.run_name}\n",
                        verification_summary="Agent verified the model endpoint.",
                    ),
                )

        agent_service = _FakeAgentService(side_effect=provision_endpoint)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.PROVISIONING
        assert endpoint_model.service_run_id is not None
        submissions = await _get_endpoint_run_submissions(
            session=session,
            endpoint_model=endpoint_model,
        )
        assert len(submissions) == 1
        assert submissions[0].run_id == endpoint_model.service_run_id

    async def test_agent_reported_run_without_verification_report_fails_endpoint(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        endpoint_model.provisioning_method = "agent"
        await session.commit()

        async def provision_endpoint(endpoint_model, pipeline_hinter):
            async with get_session_ctx() as provisioning_session:
                res = await provisioning_session.execute(
                    select(EndpointModel)
                    .where(EndpointModel.id == endpoint_model.id)
                    .options(joinedload(EndpointModel.project))
                    .options(joinedload(EndpointModel.user))
                )
                provisioning_endpoint = res.unique().scalar_one()
                run = await _create_backing_service_run(
                    session=provisioning_session,
                    endpoint_model=provisioning_endpoint,
                    link_endpoint=False,
                )
                return AgentProvisioningResult(run_id=run.id)

        agent_service = _FakeAgentService(side_effect=provision_endpoint)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.service_run_id is None
        assert endpoint_model.status_message == "Server agent did not return a verification report"

    async def test_agent_failure_fails_endpoint(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        endpoint_model.provisioning_method = "agent"
        await session.commit()
        agent_service = _FakeAgentService(
            result=AgentProvisioningResult(error="agent could not find a deployable recipe")
        )

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "agent could not find a deployable recipe"
        agent_service.provision_endpoint.assert_awaited_once()

    async def test_agent_error_status_message_is_compact(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        endpoint_model.provisioning_method = "agent"
        await session.commit()
        long_error = "agent failed before report\n" + "\n".join(
            f"offer {i:04d} gpu=A5000 price=0.27" for i in range(200)
        )
        agent_service = _FakeAgentService(result=AgentProvisioningResult(error=long_error))

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message is not None
        assert len(endpoint_model.status_message) <= 500
        assert "\n" not in endpoint_model.status_message
        assert endpoint_model.status_message.startswith("agent failed before report offer 0000")
        assert "offer 0199" not in endpoint_model.status_message

    async def test_agent_failure_report_status_message_is_compact(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        endpoint_model.provisioning_method = "agent"
        await session.commit()
        long_failure_summary = "agent could not verify service\n" + "\n".join(
            f"line {i:04d} with detailed output" for i in range(200)
        )
        agent_service = _FakeAgentService(
            result=AgentProvisioningResult(
                final_report=AgentFinalReport(
                    success=False,
                    failure_summary=long_failure_summary,
                )
            )
        )

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message is not None
        assert len(endpoint_model.status_message) <= 500
        assert "\n" not in endpoint_model.status_message
        assert endpoint_model.status_message.startswith("agent could not verify service line 0000")
        assert "line 0199" not in endpoint_model.status_message

    async def test_agent_failure_does_not_stop_unlinked_same_name_run(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.AGENTING,
        )
        endpoint_model.provisioning_method = "agent"
        await session.commit()
        created_run_id = None

        async def provision_endpoint(endpoint_model, pipeline_hinter):
            nonlocal created_run_id
            async with get_session_ctx() as agent_session:
                res = await agent_session.execute(
                    select(EndpointModel)
                    .where(EndpointModel.id == endpoint_model.id)
                    .options(joinedload(EndpointModel.project))
                    .options(joinedload(EndpointModel.user))
                )
                endpoint = res.unique().scalar_one()
                run = await _create_backing_service_run(
                    session=agent_session,
                    endpoint_model=endpoint,
                    link_endpoint=False,
                )
                created_run_id = run.id
            return AgentProvisioningResult(error="agent could not verify the service")

        agent_service = _FakeAgentService(side_effect=provision_endpoint)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints.get_agent_service",
            return_value=agent_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        assert created_run_id is not None
        await session.refresh(endpoint_model)
        run = await session.get(RunModel, created_run_id)
        assert run is not None
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "agent could not verify the service"
        assert endpoint_model.service_run_id is None
        assert run.status == RunStatus.RUNNING
        agent_service.provision_endpoint.assert_awaited_once()

    async def test_waits_when_backing_run_is_not_ready(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.PROVISIONING,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.PROVISIONING
        assert endpoint_model.status_message is None
        events = await list_events(session)
        assert events == []

    async def test_moves_to_running_when_backing_service_is_ready(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        await _create_backing_service_run(session=session, endpoint_model=endpoint_model)

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.RUNNING
        assert endpoint_model.status_message is None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint status changed PROVISIONING -> RUNNING"

    async def test_saves_preset_when_agent_backing_service_becomes_running(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        endpoint_model.provisioning_method = "agent"
        await _create_backing_service_run(session=session, endpoint_model=endpoint_model)
        preset_service = Mock()
        preset_service.save_preset = AsyncMock(side_effect=lambda preset, comments: preset)

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints."
            "get_endpoint_preset_service",
            return_value=preset_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.RUNNING
        preset_service.save_preset.assert_awaited_once()
        saved_preset = preset_service.save_preset.await_args.args[0]
        assert saved_preset.model == "Qwen/Qwen3-0.6B"
        assert [group.name for group in saved_preset.replica_spec_groups] == ["0"]
        comments = preset_service.save_preset.await_args.kwargs["comments"]
        assert f"endpoint: {endpoint_model.name}" in comments

    async def test_preset_save_failure_does_not_block_agent_endpoint_activation(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        endpoint_model.provisioning_method = "agent"
        await _create_backing_service_run(session=session, endpoint_model=endpoint_model)
        preset_service = Mock()
        preset_service.save_preset = AsyncMock(side_effect=OSError("read-only preset dir"))

        with patch(
            "dstack._internal.server.background.pipeline_tasks.endpoints."
            "get_endpoint_preset_service",
            return_value=preset_service,
        ):
            await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.RUNNING
        preset_service.save_preset.assert_awaited_once()

    async def test_waits_when_backing_service_has_no_registered_jobs(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            registered=False,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.PROVISIONING
        assert endpoint_model.status_message is None
        events = await list_events(session)
        assert events == []

    async def test_fails_when_backing_run_finished(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.FAILED,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "Backing service run finished with status failed"
        assert run.status == RunStatus.FAILED
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Endpoint status changed PROVISIONING -> FAILED "
            "(Backing service run finished with status failed)"
        )

    async def test_stops_running_backing_run_when_endpoint_fails(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.PROVISIONING,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
        )
        run.service_spec = "invalid"
        await session.commit()

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "Backing service spec is invalid"
        assert run.status == RunStatus.TERMINATING
        events = await list_events(session)
        messages = [event.message for event in events]
        assert any(
            message.startswith("Run status changed RUNNING -> TERMINATING") for message in messages
        )
        assert (
            "Endpoint status changed PROVISIONING -> FAILED "
            "(Backing service spec is invalid)" in messages
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestEndpointWorkerActive:
    async def test_ready_backing_service_keeps_endpoint_active(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
        )
        endpoint_model.status_message = "previous failure"
        await _create_backing_service_run(session=session, endpoint_model=endpoint_model)

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.RUNNING
        assert endpoint_model.status_message is None
        events = await list_events(session)
        assert events == []

    async def test_not_ready_backing_service_keeps_endpoint_active(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
        )
        await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            registered=False,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.RUNNING
        assert endpoint_model.status_message is None
        events = await list_events(session)
        assert events == []

    async def test_finished_backing_run_fails_endpoint(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.FAILED,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "Backing service run finished with status failed"
        assert run.status == RunStatus.FAILED
        events = await list_events(session)
        assert len(events) == 1
        assert (
            events[0].message == "Endpoint status changed RUNNING -> FAILED "
            "(Backing service run finished with status failed)"
        )

    async def test_stops_running_backing_run_when_endpoint_fails(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
        )
        run.service_spec = "invalid"
        await session.commit()

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.status == EndpointStatus.FAILED
        assert endpoint_model.status_message == "Backing service spec is invalid"
        assert run.status == RunStatus.TERMINATING
        events = await list_events(session)
        messages = [event.message for event in events]
        assert any(
            message.startswith("Run status changed RUNNING -> TERMINATING") for message in messages
        )
        assert (
            "Endpoint status changed RUNNING -> FAILED (Backing service spec is invalid)"
            in messages
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
class TestEndpointWorkerDeleted:
    async def test_marks_endpoint_deleted(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.FAILED,
            to_be_deleted=True,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        assert endpoint_model.deleted is True
        assert endpoint_model.deleted_at is not None
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint deleted"

    async def test_stops_active_backing_run_before_deleting_endpoint(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
            to_be_deleted=True,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.RUNNING,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.deleted is False
        assert endpoint_model.deleted_at is None
        assert run.status == RunStatus.TERMINATING
        assert run.deleted is False

    async def test_deletes_endpoint_without_stopping_unlinked_same_name_run(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
            to_be_deleted=True,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.RUNNING,
            link_endpoint=False,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.deleted is True
        assert endpoint_model.deleted_at is not None
        assert endpoint_model.service_run_id is None
        assert run.status == RunStatus.RUNNING
        assert run.deleted is False

    async def test_deletes_finished_backing_run_before_deleting_endpoint(
        self, test_db, session: AsyncSession, worker: EndpointWorker
    ):
        endpoint_model = await _create_endpoint_model(
            session=session,
            status=EndpointStatus.RUNNING,
            to_be_deleted=True,
        )
        run = await _create_backing_service_run(
            session=session,
            endpoint_model=endpoint_model,
            status=RunStatus.TERMINATED,
        )

        await worker.process(_endpoint_to_pipeline_item(endpoint_model))

        await session.refresh(endpoint_model)
        await session.refresh(run)
        assert endpoint_model.deleted is True
        assert endpoint_model.deleted_at is not None
        assert run.deleted is True
        events = await list_events(session)
        assert [event.message for event in events] == [
            "Run deleted",
            "Endpoint deleted",
        ]
