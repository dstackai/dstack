from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    Resources,
)
from dstack._internal.core.models.profiles import CreationPolicy
from dstack._internal.core.models.runs import JobStatus, RunSpec, RunStatus
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.services.endpoints.names import get_endpoint_serving_run_name
from dstack._internal.server.services.endpoints.planning import (
    build_preset_run_spec,
    build_preset_service_configuration,
    find_matching_preset_plan,
    find_preset_planning_result,
)
from dstack._internal.server.services.endpoints.preset_building import (
    build_endpoint_preset_from_run,
)
from dstack._internal.server.services.endpoints.presets import (
    EndpointPreset,
    EndpointPresetReplicaSpecGroup,
    LocalDirEndpointPresetService,
)
from dstack._internal.server.testing.common import (
    create_job,
    create_project,
    create_repo,
    create_run,
    create_user,
    get_job_runtime_data,
)

PROJECT_NAME = "test_project"


class TestLocalDirEndpointPresetService:
    @pytest.mark.asyncio
    async def test_lists_valid_endpoint_presets(self, tmp_path):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen.dstack.yml").write_text(
            """\
model: Qwen/Qwen3-4B
type: endpoint-preset
service:
  image: vllm/vllm-openai:latest
  commands:
    - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
  port: 8000
replica_spec_groups:
  - resources:
      gpu: 16GB
    tested_resources:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
"""
        )

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert len(presets) == 1
        assert presets[0].name == "qwen"
        assert presets[0].model == "Qwen/Qwen3-4B"
        assert len(presets[0].replica_spec_groups) == 1
        assert presets[0].replica_spec_groups[0].name == "0"
        assert presets[0].replica_spec_groups[0].resources.gpu is not None
        assert presets[0].replica_spec_groups[0].tested_resources[0].gpu is not None
        assert presets[0].configuration.resources.gpu is not None

    @pytest.mark.asyncio
    async def test_lists_replica_group_presets_in_group_order(self, tmp_path):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen.yml").write_text(
            """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  port: 8000
  model: Qwen/Qwen3-4B
  replicas:
    - name: router
      count: 1
      image: ghcr.io/example/router:latest
      commands:
        - python router.py
    - name: worker
      count: 2
      image: vllm/vllm-openai:latest
      commands:
        - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
replica_spec_groups:
  - name: router
    resources:
      cpu: 4
    tested_resources:
      - cpu: 8
        memory: 16GB
        disk: 100GB
        gpu: 0
  - name: worker
    resources:
      gpu: 24GB
    tested_resources:
      - cpu: 14
        memory: 64GB
        disk: 200GB
        gpu:
          name: L4
          memory: 24GB
          count: 1
      - cpu: 14
        memory: 64GB
        disk: 200GB
        gpu:
          name: L4
          memory: 24GB
          count: 1
"""
        )

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert len(presets) == 1
        assert [group.name for group in presets[0].replica_spec_groups] == ["router", "worker"]
        replica_groups = presets[0].configuration.replica_groups
        assert [group.name for group in replica_groups] == ["router", "worker"]
        assert replica_groups[0].resources.gpu is not None
        assert replica_groups[0].resources.gpu.count.min == 0
        assert replica_groups[0].resources.cpu.count.min == 4
        assert replica_groups[1].resources.gpu is not None

    @pytest.mark.asyncio
    async def test_saves_preset_without_overwriting(self, tmp_path):
        preset = _qwen_preset(name="qwen")
        service = LocalDirEndpointPresetService(tmp_path)

        saved = await service.save_preset(
            PROJECT_NAME,
            preset,
            comments=[
                "endpoint: qwen-endpoint",
                "run: 00000000-0000-0000-0000-000000000001",
            ],
        )
        saved_again = await service.save_preset(PROJECT_NAME, preset)

        assert saved.name == "qwen"
        assert saved_again.name == "qwen-2"
        presets_dir = _project_presets_dir(tmp_path)
        assert (presets_dir / "qwen.dstack.yml").exists()
        assert (presets_dir / "qwen-2.dstack.yml").exists()
        text = (presets_dir / "qwen.dstack.yml").read_text()
        assert text.startswith(
            "# endpoint: qwen-endpoint\n# run: 00000000-0000-0000-0000-000000000001\n"
        )
        assert "SECRET_VALUE" not in text
        assert "preset-service-name" not in text
        assert "creation_policy" not in text
        assert "tested_resources:" in text
        assert "HF_HOME=/root/.cache/huggingface" in text
        assert "HF_TOKEN" in text

    @pytest.mark.asyncio
    async def test_saved_preset_round_trips(self, tmp_path):
        saved = await LocalDirEndpointPresetService(tmp_path).save_preset(
            PROJECT_NAME,
            _qwen_preset(name="Qwen/Qwen3-4B vLLM"),
        )

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert saved.name == "qwen-qwen3-4b-vllm"
        assert len(presets) == 1
        assert presets[0].name == saved.name
        assert presets[0].model == "Qwen/Qwen3-4B"
        assert presets[0].configuration.model is not None
        assert presets[0].configuration.model.name == "Qwen/Qwen3-4B"
        assert set(presets[0].configuration.env.keys()) == {"HF_HOME", "HF_TOKEN"}
        assert presets[0].configuration.env["HF_HOME"] == "/root/.cache/huggingface"
        assert presets[0].configuration.resources.gpu is not None

    @pytest.mark.asyncio
    async def test_deletes_preset_by_name(self, tmp_path):
        service = LocalDirEndpointPresetService(tmp_path)
        saved = await service.save_preset(PROJECT_NAME, _qwen_preset(name="qwen"))

        await service.delete_preset(PROJECT_NAME, saved.name)

        assert await service.list_presets(PROJECT_NAME) == []
        assert not (_project_presets_dir(tmp_path) / "qwen.dstack.yml").exists()

    @pytest.mark.asyncio
    async def test_delete_missing_preset_raises(self, tmp_path):
        service = LocalDirEndpointPresetService(tmp_path)

        with pytest.raises(FileNotFoundError):
            await service.delete_preset(PROJECT_NAME, "missing")

    @pytest.mark.asyncio
    async def test_ignores_non_yaml_files(self, tmp_path):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "notes.txt").write_text("ignored")

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert presets == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("filename", "content", "message"),
        [
            (
                "task.yml",
                "type: task\ncommands:\n  - echo nope\n",
                "preset must be an endpoint preset",
            ),
            (
                "missing-model.yml",
                """\
type: endpoint-preset
service:
  commands:
    - python -m http.server 8000
  port: 8000
replica_spec_groups:
  - resources:
      gpu: 16GB
    tested_resources:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu: 0
""",
                "preset must specify a model",
            ),
            (
                "mixed-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  commands:
    - python -m http.server 8000
  port: 8000
  resources:
    gpu: 24GB
replica_spec_groups:
  - resources:
      gpu: 16GB
    tested_resources:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
""",
                "preset service object must not specify resources",
            ),
            (
                "service-profile.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  commands:
    - python -m http.server 8000
  port: 8000
  creation_policy: reuse
replica_spec_groups:
  - resources:
      gpu: 16GB
    tested_resources:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
""",
                "preset service object must not specify profile fields",
            ),
            (
                "group-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  port: 8000
  replicas:
    - name: worker
      count: 1
      image: vllm/vllm-openai:latest
      resources:
        gpu: 24GB
replica_spec_groups:
  - name: worker
    replica_specs:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
""",
                "preset service replica groups must not specify resources",
            ),
            (
                "missing-replica-spec-groups.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  port: 8000
  replicas:
    - name: worker
      count: 1
      image: vllm/vllm-openai:latest
""",
                "preset must specify non-empty replica_spec_groups",
            ),
            (
                "loose-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  commands:
    - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
  port: 8000
replica_spec_groups:
  - replica_specs:
      - gpu: 16GB
""",
                "preset tested_resources must use exact replica resources",
            ),
            (
                "mismatched-replica-spec-groups.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  port: 8000
  replicas:
    - name: worker
      count: 1
      image: vllm/vllm-openai:latest
replica_spec_groups:
  - name: other
    replica_specs:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
""",
                "preset replica_spec_groups must match replica group order",
            ),
            (
                "missing-tested-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  port: 8000
  replicas:
    - name: worker
      count: 1
      image: vllm/vllm-openai:latest
replica_spec_groups:
  - name: worker
    resources:
      gpu: 16GB
""",
                "preset replica_spec_groups must specify resources and tested_resources",
            ),
            (
                "bad-replica-group-shape.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  port: 8000
  replicas:
    - worker
replica_spec_groups:
  - name: worker
    replica_specs:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
""",
                "preset service replica groups must be objects",
            ),
            ("not-yaml.yml", ":\n", "while parsing a block mapping"),
        ],
    )
    async def test_invalid_preset_is_skipped_and_logged(
        self, tmp_path, caplog, filename, content, message
    ):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / filename).write_text(content)

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert presets == []
        assert filename in caplog.text
        assert message in caplog.text


class TestBuildEndpointPresetFromRun:
    @pytest.mark.asyncio
    async def test_builds_implicit_replica_group_from_running_service(
        self, session: AsyncSession, tmp_path
    ):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="qwen-endpoint",
            status=RunStatus.RUNNING,
            run_spec=RunSpec(
                run_name="qwen-endpoint",
                configuration=ServiceConfiguration.parse_obj(
                    {
                        "type": "service",
                        "name": "qwen-endpoint",
                        "commands": [
                            "vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000",
                        ],
                        "port": 8000,
                        "model": "Qwen/Qwen3-4B",
                        "resources": {"gpu": "16GB"},
                    }
                ),
            ),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            registered=True,
            job_runtime_data=get_job_runtime_data(
                offer=_instance_offer(gpu_name="L4", gpu_memory_gib=24, cpu_count=14)
            ),
        )
        await session.refresh(run, attribute_names=["jobs"])

        preset = build_endpoint_preset_from_run("qwen-learned", run)
        saved = await LocalDirEndpointPresetService(tmp_path).save_preset(PROJECT_NAME, preset)

        assert saved.name == "qwen-learned"
        assert saved.model == "Qwen/Qwen3-4B"
        assert [group.name for group in saved.replica_spec_groups] == ["0"]
        assert "gpu=16GB" in saved.replica_spec_groups[0].resources.pretty_format()
        tested_resources = saved.replica_spec_groups[0].tested_resources[0].pretty_format()
        assert "cpu=14" in tested_resources
        assert "gpu=L4:24GB:1" in tested_resources

    @pytest.mark.asyncio
    async def test_requires_actual_instance_resources(self, session: AsyncSession):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="qwen-endpoint",
            status=RunStatus.RUNNING,
            run_spec=RunSpec(
                run_name="qwen-endpoint",
                configuration=ServiceConfiguration.parse_obj(
                    {
                        "type": "service",
                        "name": "qwen-endpoint",
                        "commands": [
                            "vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000",
                        ],
                        "port": 8000,
                        "model": "Qwen/Qwen3-4B",
                        "resources": {"gpu": "16GB"},
                    }
                ),
            ),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            registered=True,
        )
        await session.refresh(run, attribute_names=["jobs"])

        with pytest.raises(ValueError, match="actual instance resources"):
            build_endpoint_preset_from_run("qwen-learned", run)

    @pytest.mark.asyncio
    async def test_builds_replica_groups_in_service_order(self, session: AsyncSession, tmp_path):
        project = await create_project(session=session)
        user = await create_user(session=session)
        repo = await create_repo(session=session, project_id=project.id)
        run = await create_run(
            session=session,
            project=project,
            repo=repo,
            user=user,
            run_name="qwen-endpoint",
            status=RunStatus.RUNNING,
            run_spec=RunSpec(
                run_name="qwen-endpoint",
                configuration=ServiceConfiguration.parse_obj(
                    {
                        "type": "service",
                        "name": "qwen-endpoint",
                        "port": 8000,
                        "model": "Qwen/Qwen3-4B",
                        "replicas": [
                            {
                                "name": "router",
                                "count": 1,
                                "commands": ["python router.py"],
                                "resources": {"cpu": 4},
                            },
                            {
                                "name": "worker",
                                "count": 2,
                                "commands": [
                                    "vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000",
                                ],
                                "resources": {"gpu": "24GB"},
                            },
                        ],
                    }
                ),
            ),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            registered=True,
            replica_num=0,
            replica_group_name="router",
            job_runtime_data=get_job_runtime_data(offer=_instance_offer(cpu_count=8, gpu_count=0)),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            registered=True,
            replica_num=1,
            replica_group_name="worker",
            job_runtime_data=get_job_runtime_data(
                offer=_instance_offer(gpu_name="L4", gpu_memory_gib=24)
            ),
        )
        await create_job(
            session=session,
            run=run,
            status=JobStatus.RUNNING,
            registered=True,
            replica_num=2,
            replica_group_name="worker",
            job_runtime_data=get_job_runtime_data(
                offer=_instance_offer(gpu_name="L4", gpu_memory_gib=24)
            ),
        )
        await session.refresh(run, attribute_names=["jobs"])

        preset = build_endpoint_preset_from_run("qwen-grouped", run)
        saved = await LocalDirEndpointPresetService(tmp_path).save_preset(PROJECT_NAME, preset)

        assert [group.name for group in saved.replica_spec_groups] == ["router", "worker"]
        assert "cpu=4" in saved.replica_spec_groups[0].resources.pretty_format()
        assert "gpu=24GB" in saved.replica_spec_groups[1].resources.pretty_format()
        assert len(saved.replica_spec_groups[0].tested_resources) == 1
        assert len(saved.replica_spec_groups[1].tested_resources) == 2
        assert [group.name for group in saved.configuration.replica_groups] == [
            "router",
            "worker",
        ]


class TestBuildPresetServiceConfiguration:
    def test_get_endpoint_serving_run_name(self):
        assert get_endpoint_serving_run_name("qwen-endpoint") == "qwen-endpoint-serving"

    def test_get_endpoint_serving_run_name_keeps_long_name_to_avoid_truncation(self):
        endpoint_name = "a" * 41

        assert get_endpoint_serving_run_name(endpoint_name) == endpoint_name

    def test_endpoint_name_env_and_profile_are_applied(self):
        preset = EndpointPreset(
            name="qwen",
            model="Qwen/Qwen3-4B",
            replica_spec_groups=[
                EndpointPresetReplicaSpecGroup.parse_obj(_t4_replica_spec_group())
            ],
            configuration=ServiceConfiguration.parse_obj(
                {
                    "type": "service",
                    "name": "preset-name",
                    "commands": [
                        "vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000",
                    ],
                    "port": 8000,
                    "model": "Qwen/Qwen3-4B",
                    "env": {"HF_HOME": "/root/.cache/huggingface", "HF_TOKEN": "preset"},
                    "resources": {"gpu": "16GB"},
                }
            ),
        )
        endpoint_configuration = EndpointConfiguration(
            name="endpoint-name",
            model="Qwen/Qwen3-4B",
            env=Env.parse_obj({"HF_TOKEN": "endpoint"}),
            creation_policy=CreationPolicy.REUSE_OR_CREATE,
            max_price=1.5,
        )

        service_configuration = build_preset_service_configuration(
            endpoint_name="endpoint-name",
            endpoint_configuration=endpoint_configuration,
            preset=preset,
        )

        assert service_configuration.name == "endpoint-name-serving"
        assert service_configuration.env.as_dict() == {
            "HF_HOME": "/root/.cache/huggingface",
            "HF_TOKEN": "endpoint",
        }
        assert service_configuration.creation_policy == CreationPolicy.REUSE_OR_CREATE
        assert service_configuration.max_price == 1.5
        assert service_configuration.resources.gpu is not None

    def test_builds_repo_less_run_spec(self):
        preset = EndpointPreset(
            name="qwen",
            model="Qwen/Qwen3-4B",
            replica_spec_groups=[
                EndpointPresetReplicaSpecGroup.parse_obj(_t4_replica_spec_group())
            ],
            configuration=ServiceConfiguration.parse_obj(
                {
                    "type": "service",
                    "commands": [
                        "vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000",
                    ],
                    "port": 8000,
                    "model": "Qwen/Qwen3-4B",
                }
            ),
        )
        endpoint_configuration = EndpointConfiguration(
            name="endpoint-name",
            model="Qwen/Qwen3-4B",
        )

        run_spec = build_preset_run_spec(
            endpoint_name="endpoint-name",
            endpoint_configuration=endpoint_configuration,
            preset=preset,
        )

        assert run_spec.run_name == "endpoint-name-serving"
        assert run_spec.repo_id is None
        assert run_spec.repo_data is None
        assert run_spec.ssh_key_pub is None
        assert run_spec.configuration.name == "endpoint-name-serving"

    @pytest.mark.asyncio
    async def test_missing_dir_returns_no_presets(self, tmp_path):
        presets = await LocalDirEndpointPresetService(tmp_path / "missing").list_presets(
            PROJECT_NAME
        )

        assert presets == []


class TestFindMatchingPreset:
    @pytest.mark.asyncio
    async def test_returns_first_preset_with_available_offers(
        self, session: AsyncSession, tmp_path
    ):
        _write_qwen_preset(tmp_path)
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)
        endpoint_configuration = EndpointConfiguration(
            name="qwen-endpoint",
            model="Qwen/Qwen3-4B",
        )

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(return_value=_run_plan_with_offer(available=True)),
        ) as get_plan_mock:
            match = await find_matching_preset_plan(
                session=session,
                project=project,
                user=user,
                endpoint_name="qwen-endpoint",
                endpoint_configuration=endpoint_configuration,
                preset_service=LocalDirEndpointPresetService(tmp_path),
            )

        assert match is not None
        assert match.preset.name == "qwen"
        get_plan_mock.assert_awaited_once()
        assert get_plan_mock.await_args is not None
        assert get_plan_mock.await_args.kwargs["run_spec"].run_name == "qwen-endpoint-serving"

    @pytest.mark.asyncio
    async def test_tracks_first_unprovisionable_preset_when_offers_are_unavailable(
        self, session: AsyncSession, tmp_path
    ):
        _write_qwen_preset(tmp_path)
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(return_value=_run_plan_with_offer(available=False)),
        ):
            result = await find_preset_planning_result(
                session=session,
                project=project,
                user=user,
                endpoint_name="qwen-endpoint",
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-endpoint",
                    model="Qwen/Qwen3-4B",
                ),
                preset_service=LocalDirEndpointPresetService(tmp_path),
            )

        assert result.provisionable is None
        assert result.unprovisionable is not None
        assert result.unprovisionable.preset.name == "qwen"

    @pytest.mark.asyncio
    async def test_matching_plan_requires_available_offers(self, session: AsyncSession, tmp_path):
        _write_qwen_preset(tmp_path)
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(return_value=_run_plan_with_offer(available=False)),
        ):
            match = await find_matching_preset_plan(
                session=session,
                project=project,
                user=user,
                endpoint_name="qwen-endpoint",
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-endpoint",
                    model="Qwen/Qwen3-4B",
                ),
                preset_service=LocalDirEndpointPresetService(tmp_path),
            )

        assert match is None

    @pytest.mark.asyncio
    async def test_skips_preset_with_unresolved_env_sentinel(
        self, session: AsyncSession, tmp_path
    ):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen.yml").write_text(
            """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  env:
    - HF_TOKEN
  commands:
    - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
  port: 8000
replica_spec_groups:
  - resources:
      gpu: 16GB
    tested_resources:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
"""
        )
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(),
        ) as get_plan_mock:
            result = await find_preset_planning_result(
                session=session,
                project=project,
                user=user,
                endpoint_name="qwen-endpoint",
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-endpoint",
                    model="Qwen/Qwen3-4B",
                ),
                preset_service=LocalDirEndpointPresetService(tmp_path),
            )

        assert result.provisionable is None
        assert result.unprovisionable is None
        get_plan_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refreshes_user_ssh_key_before_planning(self, session: AsyncSession, tmp_path):
        _write_qwen_preset(tmp_path)
        user = await create_user(session=session, global_role=GlobalRole.USER)
        project = await create_project(session=session, owner=user)
        user.ssh_public_key = None
        await session.commit()

        with (
            patch(
                "dstack._internal.server.services.endpoints.planning.users_services.refresh_ssh_key",
                new=AsyncMock(return_value=user),
            ) as refresh_mock,
            patch(
                "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
                new=AsyncMock(return_value=_run_plan_with_offer(available=True)),
            ),
        ):
            match = await find_matching_preset_plan(
                session=session,
                project=project,
                user=user,
                endpoint_name="qwen-endpoint",
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-endpoint",
                    model="Qwen/Qwen3-4B",
                ),
                preset_service=LocalDirEndpointPresetService(tmp_path),
            )

        assert match is not None
        refresh_mock.assert_awaited_once()


def _write_qwen_preset(tmp_path):
    presets_dir = _project_presets_dir(tmp_path)
    presets_dir.mkdir(parents=True)
    (presets_dir / "qwen.yml").write_text(
        """\
type: endpoint-preset
model: Qwen/Qwen3-4B
service:
  commands:
    - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
  port: 8000
replica_spec_groups:
  - resources:
      gpu: 16GB
    tested_resources:
      - cpu: 4
        memory: 16GB
        disk: 100GB
        gpu:
          name: T4
          memory: 16GB
          count: 1
"""
    )


def _project_presets_dir(projects_dir):
    return projects_dir / PROJECT_NAME / "presets"


def _instance_offer(
    gpu_name: str = "T4",
    gpu_memory_gib: float = 16,
    gpu_count: int = 1,
    cpu_count: int = 4,
    memory_gib: float = 16,
    disk_gib: float = 100,
) -> InstanceOfferWithAvailability:
    return InstanceOfferWithAvailability(
        backend=BackendType.AWS,
        instance=InstanceType(
            name="test-instance",
            resources=Resources(
                cpus=cpu_count,
                memory_mib=int(memory_gib * 1024),
                gpus=[
                    Gpu(
                        name=gpu_name,
                        memory_mib=int(gpu_memory_gib * 1024),
                    )
                    for _ in range(gpu_count)
                ],
                spot=False,
                disk=Disk(size_mib=int(disk_gib * 1024)),
            ),
        ),
        region="us-east-1",
        price=1.0,
        availability=InstanceAvailability.AVAILABLE,
        instance_runtime=InstanceRuntime.SHIM,
    )


def _qwen_preset(name: str) -> EndpointPreset:
    return EndpointPreset(
        name=name,
        model="Qwen/Qwen3-4B",
        replica_spec_groups=[EndpointPresetReplicaSpecGroup.parse_obj(_t4_replica_spec_group())],
        configuration=ServiceConfiguration.parse_obj(
            {
                "type": "service",
                "name": "preset-service-name",
                "commands": [
                    "vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000",
                ],
                "port": 8000,
                "model": "Qwen/Qwen3-4B",
                "env": {
                    "HF_HOME": "/root/.cache/huggingface",
                    "HF_TOKEN": "SECRET_VALUE",
                },
                "resources": {"gpu": "16GB"},
                "creation_policy": "reuse",
            }
        ),
    )


def _t4_replica_spec_group() -> dict:
    return {
        "name": "0",
        "resources": {"gpu": "16GB"},
        "tested_resources": [
            {
                "cpu": 4,
                "memory": "16GB",
                "disk": "100GB",
                "gpu": {"name": "T4", "memory": "16GB", "count": 1},
            }
        ],
    }


def _run_plan_with_offer(available: bool):
    availability = Mock()
    availability.is_available.return_value = available
    offer = Mock(availability=availability)
    job_plan = Mock(offers=[offer])
    job_plan.job_spec.requirements.resources = Mock()
    job_plan.job_spec.requirements.spot = None
    job_plan.job_spec.requirements.max_price = None
    return Mock(job_plans=[job_plan])
