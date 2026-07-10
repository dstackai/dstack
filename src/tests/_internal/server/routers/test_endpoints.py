from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
from freezegun import freeze_time
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoints import (
    EndpointConfiguration,
    EndpointStatus,
)
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceOfferWithAvailability,
)
from dstack._internal.core.models.runs import RunSpec, RunStatus
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import EndpointModel
from dstack._internal.server.services.endpoints.agent import AgentPlan
from dstack._internal.server.services.endpoints.planning import (
    EndpointPresetPlan,
    EndpointPresetPlanningResult,
)
from dstack._internal.server.services.endpoints.presets import (
    EndpointPreset,
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
)
from dstack._internal.server.services.projects import add_project_member
from dstack._internal.server.testing.common import (
    create_fleet,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_auth_headers,
    list_events,
)


class TestEndpointPlan:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/get_plan")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_none_provisioning_plan(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_fleet(session=session, project=project)

        with patch(
            "dstack._internal.server.services.endpoints.find_preset_planning_result",
            new=AsyncMock(return_value=EndpointPresetPlanningResult()),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                        "env": {"HF_TOKEN": "secret"},
                    },
                    "configuration_path": "endpoint.dstack.yml",
                },
            )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["project_name"] == project.name
        assert body["user"] == user.name
        assert body["configuration"]["model"] == {
            "repo": "Qwen/Qwen3-0.6B",
            "name": None,
        }
        assert body["configuration_path"] == "endpoint.dstack.yml"
        assert body["current_resource"] is None
        assert body["action"] == "create"
        assert body["preset_policy"] == "reuse-or-create"
        assert body["provisioning_plan"] == {
            "type": "none",
            "reason": (
                "No matching endpoint presets found. "
                "Creating a preset requires the server agent, but "
                "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
            ),
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_create_plan_when_existing_endpoint_is_terminal(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.FAILED,
        )

        with patch(
            "dstack._internal.server.services.endpoints.find_preset_planning_result",
            new=AsyncMock(return_value=EndpointPresetPlanningResult()),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    },
                },
            )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["current_resource"] is None
        assert body["action"] == "create"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_agent_provisioning_plan(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_fleet(session=session, project=project)
        agent_service = Mock()
        agent_service.is_enabled.return_value = True
        agent_service.get_plan.return_value = AgentPlan(model="test-agent")

        with (
            patch(
                "dstack._internal.server.services.endpoints.find_preset_planning_result",
                new=AsyncMock(return_value=EndpointPresetPlanningResult()),
            ),
            patch(
                "dstack._internal.server.services.endpoints.get_agent_service",
                return_value=agent_service,
            ),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    },
                    "configuration_path": "endpoint.dstack.yml",
                },
            )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["preset_policy"] == "reuse-or-create"
        assert body["provisioning_plan"] == {
            "type": "agent",
            "agent_model": "test-agent",
            "reason": None,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_no_agent_plan_without_existing_fleets(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        agent_service = Mock()
        agent_service.is_enabled.return_value = True
        agent_service.get_plan.return_value = AgentPlan(model="test-agent")

        with (
            patch(
                "dstack._internal.server.services.endpoints.find_preset_planning_result",
                new=AsyncMock(return_value=EndpointPresetPlanningResult()),
            ),
            patch(
                "dstack._internal.server.services.endpoints.get_agent_service",
                return_value=agent_service,
            ),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    },
                    "configuration_path": "endpoint.dstack.yml",
                },
            )

        assert response.status_code == 200, response.json()
        assert response.json()["provisioning_plan"] == {
            "type": "none",
            "reason": "The project has no fleets. Create one before submitting an endpoint.",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_no_fleets_plan_for_reuse_without_existing_fleets(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/get_plan",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                    "preset_policy": "reuse",
                },
                "configuration_path": "endpoint.dstack.yml",
            },
        )

        assert response.status_code == 200, response.json()
        assert response.json()["provisioning_plan"] == {
            "type": "none",
            "reason": "The project has no fleets. Create one before submitting an endpoint.",
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_no_agent_plan_when_configured_fleet_does_not_match(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_fleet(session=session, project=project, name="existing-fleet")
        agent_service = Mock()
        agent_service.is_enabled.return_value = True
        agent_service.get_plan.return_value = AgentPlan(model="test-agent")

        with (
            patch(
                "dstack._internal.server.services.endpoints.find_preset_planning_result",
                new=AsyncMock(return_value=EndpointPresetPlanningResult()),
            ),
            patch(
                "dstack._internal.server.services.endpoints.get_agent_service",
                return_value=agent_service,
            ),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                        "fleets": ["missing-fleet"],
                    },
                    "configuration_path": "endpoint.dstack.yml",
                },
            )

        assert response.status_code == 200, response.json()
        assert response.json()["provisioning_plan"] == {
            "type": "none",
            "reason": (
                "No fleets match the endpoint configuration. Create a fleet or update `fleets` "
                "before submitting an endpoint."
            ),
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_no_agent_plan_for_project_user(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_fleet(session=session, project=project)
        agent_service = Mock()
        agent_service.is_enabled.return_value = True

        with (
            patch(
                "dstack._internal.server.services.endpoints.find_preset_planning_result",
                new=AsyncMock(return_value=EndpointPresetPlanningResult()),
            ),
            patch(
                "dstack._internal.server.services.endpoints.get_agent_service",
                return_value=agent_service,
            ),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    },
                },
            )

        assert response.status_code == 200, response.json()
        assert response.json()["provisioning_plan"] == {
            "type": "none",
            "reason": (
                "No matching endpoint presets found. "
                "Creating endpoint presets with the server agent requires project admin "
                "permissions."
            ),
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_returns_preset_provisioning_plan(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_fleet(session=session, project=project)

        with patch(
            "dstack._internal.server.services.endpoints.find_preset_planning_result",
            new=AsyncMock(
                return_value=EndpointPresetPlanningResult(provisionable=_endpoint_preset_plan())
            ),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/get_plan",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    },
                },
            )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["provisioning_plan"]["type"] == "preset"
        assert body["preset_policy"] == "reuse-or-create"
        assert body["provisioning_plan"]["preset_base"] == "Qwen/Qwen3-0.6B"
        assert body["provisioning_plan"]["recipe_id"] == "vllm-t4"
        assert body["provisioning_plan"]["service_name"] == "qwen-endpoint-serving"
        assert body["provisioning_plan"]["job_offers"][0]["replica_group"] == "0"
        assert body["provisioning_plan"]["job_offers"][0]["resources"]["gpu"] is not None
        assert body["provisioning_plan"]["job_offers"][0]["spot"] is None
        assert body["provisioning_plan"]["job_offers"][0]["max_price"] is None
        assert body["provisioning_plan"]["job_offers"][0]["offers"][0]["backend"] == "aws"
        assert body["provisioning_plan"]["job_offers"][0]["total_offers"] == 2


class TestCreateEndpoint:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/create")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    @freeze_time(datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc))
    async def test_creates_endpoint(self, test_db, session: AsyncSession, client: AsyncClient):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_fleet(session=session, project=project)

        response = await client.post(
            f"/api/project/{project.name}/endpoints/create",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                    "env": {"HF_TOKEN": "secret"},
                }
            },
        )

        assert response.status_code == 200, response.json()
        body = response.json()
        UUID(body["id"])
        assert body["name"] == "qwen-endpoint"
        assert body["project_name"] == project.name
        assert body["user"] == user.name
        assert body["configuration"]["model"] == {
            "repo": "Qwen/Qwen3-0.6B",
            "name": None,
        }
        assert body["configuration"]["env"] == {"HF_TOKEN": "secret"}
        assert body["created_at"] == "2023-01-02T03:04:00+00:00"
        assert body["last_processed_at"] == "2023-01-02T03:04:00+00:00"
        assert body["status"] == "submitted"
        assert body["status_message"] is None
        assert body["run_name"] is None
        assert body["url"] is None
        assert body["error"] is None

        res = await session.execute(select(EndpointModel))
        assert res.scalar_one()
        events = await list_events(session)
        assert len(events) == 1
        assert events[0].message == "Endpoint created. Status: SUBMITTED"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_rejects_create_without_existing_fleets(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        with patch(
            "dstack._internal.server.services.endpoints.find_preset_planning_result",
            new=AsyncMock(return_value=EndpointPresetPlanningResult()),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/create",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    }
                },
            )

        assert response.status_code == 400
        assert response.json()["detail"][0]["msg"] == (
            "The project has no fleets. Create one before submitting an endpoint."
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_rejects_reuse_without_existing_fleets(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/create",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                    "preset_policy": "reuse",
                }
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"][0]["msg"] == (
            "The project has no fleets. Create one before submitting an endpoint."
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_resubmits_terminal_endpoint(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await create_fleet(session=session, project=project)
        previous_endpoint = await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.FAILED,
        )
        previous_endpoint.status_message = "old failure"
        await session.commit()

        response = await client.post(
            f"/api/project/{project.name}/endpoints/create",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                }
            },
        )

        assert response.status_code == 200, response.json()
        endpoint_id = UUID(response.json()["id"])
        assert endpoint_id == previous_endpoint.id
        await session.refresh(previous_endpoint)
        assert previous_endpoint.status == EndpointStatus.SUBMITTED
        assert previous_endpoint.status_message is None
        assert previous_endpoint.service_run_id is None
        assert previous_endpoint.configuration != ""
        res = await session.execute(select(EndpointModel))
        assert len(res.scalars().all()) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_rejects_resubmit_terminal_endpoint_without_existing_fleets(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        previous_endpoint = await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.FAILED,
        )
        previous_endpoint.status_message = "old failure"
        await session.commit()

        response = await client.post(
            f"/api/project/{project.name}/endpoints/create",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                }
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"][0]["msg"] == (
            "The project has no fleets. Create one before submitting an endpoint."
        )
        await session.refresh(previous_endpoint)
        assert previous_endpoint.status == EndpointStatus.FAILED
        assert previous_endpoint.status_message == "old failure"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_rejects_project_user_when_create_requires_agent(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_fleet(session=session, project=project)

        with patch(
            "dstack._internal.server.services.endpoints.find_preset_planning_result",
            new=AsyncMock(return_value=EndpointPresetPlanningResult()),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/create",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    }
                },
            )

        assert response.status_code == 403
        assert response.json()["msg"] == (
            "Creating endpoint presets with the server agent requires project admin permissions."
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_allows_project_user_when_matching_preset_exists(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        await create_fleet(session=session, project=project)

        with patch(
            "dstack._internal.server.services.endpoints.find_preset_planning_result",
            new=AsyncMock(
                return_value=EndpointPresetPlanningResult(provisionable=_endpoint_preset_plan())
            ),
        ):
            response = await client.post(
                f"/api/project/{project.name}/endpoints/create",
                headers=get_auth_headers(user.token),
                json={
                    "configuration": {
                        "type": "endpoint",
                        "name": "qwen-endpoint",
                        "model": "Qwen/Qwen3-0.6B",
                    }
                },
            )

        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "submitted"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_rejects_duplicate_non_terminal_endpoint(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.ADMIN
        )
        await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.SUBMITTED,
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/create",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                }
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"][0]["code"] == "resource_exists"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_rejects_unresolved_env_sentinel(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/create",
            headers=get_auth_headers(user.token),
            json={
                "configuration": {
                    "type": "endpoint",
                    "name": "qwen-endpoint",
                    "model": "Qwen/Qwen3-0.6B",
                    "env": ["HF_TOKEN"],
                }
            },
        )

        assert response.status_code == 400
        assert "Endpoint env is unresolved" in response.json()["detail"][0]["msg"]


class TestGetEndpoint:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_stopped_endpoint_hides_linked_run_name(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        endpoint_model = await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.STOPPED,
        )
        repo = await create_repo(
            session=session,
            project_id=project.id,
            repo_name="qwen-endpoint-serving-repo",
        )
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="qwen-endpoint-serving",
            status=RunStatus.TERMINATED,
        )
        endpoint_model.service_run_id = run.id
        await session.commit()

        response = await client.post(
            f"/api/project/{project.name}/endpoints/get",
            headers=get_auth_headers(user.token),
            json={"name": endpoint_model.name},
        )

        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "stopped"
        assert response.json()["run_name"] is None


class TestStopEndpoint:
    @pytest.mark.asyncio
    async def test_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/stop")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_marks_endpoint_for_stopping(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        endpoint_model = await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.RUNNING,
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/stop",
            headers=get_auth_headers(user.token),
            json={"names": [endpoint_model.name]},
        )

        assert response.status_code == 200, response.json()
        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.STOPPING
        events = await list_events(session)
        assert [e.message for e in events] == ["Endpoint marked for stopping"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_does_not_stop_finished_endpoint(
        self, test_db, session: AsyncSession, client: AsyncClient
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        endpoint_model = await _create_endpoint_model(
            session=session,
            project=project,
            user=user,
            status=EndpointStatus.FAILED,
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/stop",
            headers=get_auth_headers(user.token),
            json={"names": [endpoint_model.name]},
        )

        assert response.status_code == 200, response.json()
        await session.refresh(endpoint_model)
        assert endpoint_model.status == EndpointStatus.FAILED
        events = await list_events(session)
        assert events == []


class TestEndpointPresets:
    @pytest.mark.asyncio
    async def test_list_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/presets/list")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_delete_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/presets/delete")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_get_returns_40x_if_not_authenticated(self, client: AsyncClient):
        response = await client.post("/api/project/main/endpoints/presets/get")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_lists_endpoint_presets(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        preset_service = _FakeEndpointPresetService([_endpoint_preset_plan().preset])
        monkeypatch.setattr(
            "dstack._internal.server.routers.endpoints.get_endpoint_preset_service",
            lambda: preset_service,
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/presets/list",
            headers=get_auth_headers(user.token),
        )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert len(body) == 1
        assert body[0]["base"] == "Qwen/Qwen3-0.6B"
        assert body[0]["recipes"][0]["id"] == "vllm-t4"
        assert body[0]["recipes"][0]["service"]["resources"]["gpu"] is not None
        assert body[0]["recipes"][0]["validations"][0]["replicas"][0]["resources"][0]["gpu"]
        assert preset_service.list_project_names == [project.name]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_deletes_endpoint_preset(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        preset_service = _FakeEndpointPresetService([_endpoint_preset_plan().preset])
        monkeypatch.setattr(
            "dstack._internal.server.routers.endpoints.get_endpoint_preset_service",
            lambda: preset_service,
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/presets/delete",
            headers=get_auth_headers(user.token),
            json={"models": ["Qwen/Qwen3-0.6B"]},
        )

        assert response.status_code == 200, response.json()
        assert preset_service.deleted_models == ["Qwen/Qwen3-0.6B"]
        assert preset_service.delete_project_names == [project.name]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_gets_endpoint_preset(
        self,
        test_db,
        session: AsyncSession,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ):
        user = await create_user(session, global_role=GlobalRole.USER)
        project = await create_project(session)
        await add_project_member(
            session=session, project=project, user=user, project_role=ProjectRole.USER
        )
        preset_service = _FakeEndpointPresetService([_endpoint_preset_plan().preset])
        monkeypatch.setattr(
            "dstack._internal.server.routers.endpoints.get_endpoint_preset_service",
            lambda: preset_service,
        )

        response = await client.post(
            f"/api/project/{project.name}/endpoints/presets/get",
            headers=get_auth_headers(user.token),
            json={"model": "Qwen/Qwen3-0.6B"},
        )

        assert response.status_code == 200, response.json()
        body = response.json()
        assert body["base"] == "Qwen/Qwen3-0.6B"
        assert body["recipes"][0]["service"]["type"] == "service"
        assert body["recipes"][0]["service"]["resources"]["gpu"] is not None
        assert preset_service.get_project_names == [project.name]


class _FakeEndpointPresetService:
    def __init__(self, presets):
        self._presets = presets
        self.list_project_names = []
        self.get_project_names = []
        self.delete_project_names = []
        self.deleted_models = []

    async def list_presets(self, project_name):
        self.list_project_names.append(project_name)
        return self._presets

    async def get_preset(self, project_name, model):
        self.get_project_names.append(project_name)
        for preset in self._presets:
            if preset.base == model:
                return preset
        return None

    async def delete_preset(self, project_name, model):
        if model not in {preset.base for preset in self._presets}:
            raise FileNotFoundError(model)
        self.delete_project_names.append(project_name)
        self.deleted_models.append(model)


async def _create_endpoint_model(
    session: AsyncSession,
    project,
    user,
    status: EndpointStatus = EndpointStatus.SUBMITTED,
    name: str = "qwen-endpoint",
) -> EndpointModel:
    configuration = EndpointConfiguration(name=name, model="Qwen/Qwen3-0.6B")
    endpoint_model = EndpointModel(
        name=name,
        project=project,
        user=user,
        configuration=configuration.json(),
        status=status,
        created_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
        last_processed_at=datetime(2023, 1, 2, 3, 4, tzinfo=timezone.utc),
    )
    session.add(endpoint_model)
    await session.commit()
    return endpoint_model


def _endpoint_preset_plan() -> EndpointPresetPlan:
    service_configuration = ServiceConfiguration.parse_obj(
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
    )
    recipe = EndpointPresetRecipe(
        id="vllm-t4",
        model="Qwen/Qwen3-0.6B",
        service=service_configuration,
        validations=[
            EndpointPresetValidation(
                replicas=[
                    EndpointPresetValidationReplica.parse_obj(
                        {
                            "resources": [
                                {
                                    "cpu": 4,
                                    "memory": "16GB",
                                    "disk": "100GB",
                                    "gpu": {"name": "T4", "memory": "16GB", "count": 1},
                                }
                            ]
                        }
                    )
                ]
            )
        ],
    )
    preset = EndpointPreset(base="Qwen/Qwen3-0.6B", recipes=[recipe])
    run_plan = Mock()
    run_plan.get_effective_run_spec.return_value = RunSpec(
        run_name="qwen-endpoint-serving",
        configuration=service_configuration,
    )
    job_plan = Mock()
    job_plan.job_spec.replica_group = "0"
    job_plan.job_spec.requirements.resources = service_configuration.resources
    job_plan.job_spec.requirements.spot = None
    job_plan.job_spec.requirements.max_price = None
    job_plan.offers = [_instance_offer()]
    job_plan.total_offers = 2
    job_plan.max_price = 1.25
    run_plan.job_plans = [job_plan]
    return EndpointPresetPlan(preset=preset, recipe=recipe, run_plan=run_plan)


def _instance_offer() -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability.parse_obj(
        {
            "backend": BackendType.AWS,
            "region": "us-east-1",
            "price": 1.25,
            "availability": InstanceAvailability.AVAILABLE,
            "instance": {
                "name": "g5.xlarge",
                "resources": {
                    "cpus": 4,
                    "memory_mib": 16384,
                    "gpus": [],
                    "spot": False,
                },
            },
        }
    )
