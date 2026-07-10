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
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
    LocalDirEndpointPresetService,
    make_endpoint_preset_recipe_id,
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
recipes:
  - id: vllm-t4
    service:
      image: vllm/vllm-openai:latest
      commands:
        - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
      port: 8000
      resources:
        gpu: 16GB
    validations:
      - replicas:
          - resources:
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
        assert presets[0].base == "Qwen/Qwen3-4B"
        assert [recipe.id for recipe in presets[0].recipes] == ["vllm-t4"]
        recipe = presets[0].recipes[0]
        assert recipe.service.resources.gpu is not None
        assert recipe.service.resources.gpu.vendor is None
        assert recipe.validations[0].replicas[0].resources[0].gpu is not None

    @pytest.mark.asyncio
    async def test_lists_replica_group_presets_in_group_order(self, tmp_path):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen.yml").write_text(
            """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: grouped
    service:
      port: 8000
      model: Qwen/Qwen3-4B
      replicas:
        - name: router
          count: 1
          image: ghcr.io/example/router:latest
          commands:
            - python router.py
          resources:
            cpu: 4
        - name: worker
          count: 2
          image: vllm/vllm-openai:latest
          commands:
            - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
          resources:
            gpu: 24GB
    validations:
      - replicas:
          - resources:
              - cpu: 8
                memory: 16GB
                disk: 100GB
                gpu: 0
          - resources:
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
        replica_groups = presets[0].recipes[0].service.replica_groups
        assert [group.name for group in replica_groups] == ["router", "worker"]
        assert replica_groups[0].resources.gpu is not None
        assert replica_groups[0].resources.gpu.count.min == 0
        assert replica_groups[0].resources.cpu.count.min == 4
        assert replica_groups[1].resources.gpu is not None

    @pytest.mark.asyncio
    async def test_loads_legacy_replica_spec_groups_as_recipe_validation(self, tmp_path):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen-legacy.yml").write_text(
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
        recipe = presets[0].recipes[0]
        assert recipe.service.resources.gpu is not None
        assert recipe.service.resources.gpu.vendor is None
        assert recipe.validations[0].replicas[0].resources[0].gpu is not None

    @pytest.mark.asyncio
    async def test_rejects_service_gpu_vendor_mismatch(self, tmp_path, caplog):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen.yml").write_text(
            """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm-amd
    service:
      commands:
        - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
      port: 8000
      resources:
        gpu: amd:16GB
    validations:
      - replicas:
          - resources:
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

        assert presets == []
        assert "preset service GPU vendor does not match validation" in caplog.text

    @pytest.mark.asyncio
    async def test_saves_preset_with_comments_and_merges_same_base(self, tmp_path):
        preset = _qwen_preset(recipe_id="vllm-t4")
        extra_preset = _qwen_preset(recipe_id="vllm-l4", resources={"gpu": "24GB"})
        service = LocalDirEndpointPresetService(tmp_path)

        saved = await service.save_preset(
            PROJECT_NAME,
            preset,
            comments=[
                "endpoint: qwen-endpoint",
                "run: 00000000-0000-0000-0000-000000000001",
            ],
        )
        assert saved.base == "Qwen/Qwen3-4B"
        presets_dir = _project_presets_dir(tmp_path)
        preset_files = list(presets_dir.glob("*.dstack.yml"))
        assert len(preset_files) == 1
        text = preset_files[0].read_text()
        assert text.startswith(
            "# endpoint: qwen-endpoint\n# run: 00000000-0000-0000-0000-000000000001\n"
        )
        assert "SECRET_VALUE" not in text
        assert "preset-service-name" not in text
        assert "creation_policy" not in text
        assert "validations:" in text
        assert saved.recipes[0].model == "Qwen/Qwen3-4B"
        assert "HF_HOME=/root/.cache/huggingface" in text
        assert "HF_TOKEN" in text
        saved_again = await service.save_preset(PROJECT_NAME, extra_preset)

        assert [recipe.id for recipe in saved_again.recipes] == ["vllm-l4", "vllm-t4"]
        assert len(list(presets_dir.glob("*.dstack.yml"))) == 1

    @pytest.mark.asyncio
    async def test_merges_duplicate_base_files_for_list_get_save_and_delete(self, tmp_path):
        service = LocalDirEndpointPresetService(tmp_path)
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        _write_qwen_preset_file(presets_dir / "qwen-a.yml", recipe_id="vllm-t4", gpu="16GB")
        _write_qwen_preset_file(presets_dir / "qwen-b.yml", recipe_id="vllm-l4", gpu="24GB")

        presets = await service.list_presets(PROJECT_NAME)
        preset = await service.get_preset(PROJECT_NAME, "Qwen/Qwen3-4B")

        assert len(presets) == 1
        assert preset is not None
        assert [recipe.id for recipe in presets[0].recipes] == ["vllm-t4", "vllm-l4"]
        assert [recipe.id for recipe in preset.recipes] == ["vllm-t4", "vllm-l4"]

        saved = await service.save_preset(
            PROJECT_NAME,
            _qwen_preset(recipe_id="vllm-a100", resources={"gpu": "80GB"}),
        )

        assert [recipe.id for recipe in saved.recipes] == ["vllm-a100", "vllm-t4", "vllm-l4"]
        assert len(list(presets_dir.glob("*.yml"))) == 1

        await service.delete_preset(PROJECT_NAME, "Qwen/Qwen3-4B")

        assert await service.list_presets(PROJECT_NAME) == []
        assert list(presets_dir.glob("*.yml")) == []

    @pytest.mark.asyncio
    async def test_saved_preset_round_trips(self, tmp_path):
        saved = await LocalDirEndpointPresetService(tmp_path).save_preset(
            PROJECT_NAME,
            _qwen_preset(recipe_id="vllm-t4"),
        )

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert saved.base == "Qwen/Qwen3-4B"
        assert len(presets) == 1
        assert presets[0].base == "Qwen/Qwen3-4B"
        recipe = presets[0].recipes[0]
        assert recipe.model == "Qwen/Qwen3-4B"
        assert recipe.service.model is not None
        assert recipe.service.model.name == "Qwen/Qwen3-4B"
        assert set(recipe.service.env.keys()) == {"HF_HOME", "HF_TOKEN"}
        assert recipe.service.env["HF_HOME"] == "/root/.cache/huggingface"
        assert recipe.service.resources.gpu is not None

    @pytest.mark.asyncio
    async def test_loads_recipe_model_that_differs_from_preset_base(self, tmp_path):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        (presets_dir / "qwen.yml").write_text(
            """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm-t4
    model: groxaxo/Qwen3-4B-GPTQ-4Bit
    service:
      commands:
        - vllm serve groxaxo/Qwen3-4B-GPTQ-4Bit --served-model-name Qwen/Qwen3-4B
      port: 8000
      model: Qwen/Qwen3-4B
      resources:
        gpu: 16GB
    validations:
      - replicas:
          - resources:
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

        recipe = presets[0].recipes[0]
        assert recipe.model == "groxaxo/Qwen3-4B-GPTQ-4Bit"
        assert recipe.service.model is not None
        assert recipe.service.model.name == "Qwen/Qwen3-4B"

    @pytest.mark.asyncio
    async def test_legacy_recipe_without_model_uses_preset_base(self, tmp_path):
        _write_qwen_preset(tmp_path)

        presets = await LocalDirEndpointPresetService(tmp_path).list_presets(PROJECT_NAME)

        assert presets[0].recipes[0].model == "Qwen/Qwen3-4B"

    @pytest.mark.asyncio
    async def test_rejects_same_recipe_id_with_different_recipe_model(self, tmp_path):
        service = LocalDirEndpointPresetService(tmp_path)
        await service.save_preset(
            PROJECT_NAME,
            _qwen_preset(recipe_id="vllm-t4", recipe_model="Qwen/Qwen3-4B-GPTQ-A"),
        )

        with pytest.raises(ValueError, match="endpoint preset recipe id conflict"):
            await service.save_preset(
                PROJECT_NAME,
                _qwen_preset(recipe_id="vllm-t4", recipe_model="Qwen/Qwen3-4B-GPTQ-B"),
            )

    @pytest.mark.asyncio
    async def test_deletes_preset_by_model(self, tmp_path):
        service = LocalDirEndpointPresetService(tmp_path)
        saved = await service.save_preset(PROJECT_NAME, _qwen_preset())

        await service.delete_preset(PROJECT_NAME, saved.base)

        assert await service.list_presets(PROJECT_NAME) == []
        assert list(_project_presets_dir(tmp_path).glob("*.dstack.yml")) == []

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
                "missing-base.yml",
                """\
type: endpoint-preset
recipes:
  - id: vllm
    service:
      commands:
        - python -m http.server 8000
      port: 8000
      resources:
        gpu: 16GB
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu: 0
""",
                "preset must specify a base",
            ),
            (
                "base-model-mismatch.yml",
                """\
type: endpoint-preset
base: Qwen/Qwen3-4B
model: Qwen/Qwen3-8B
recipes:
  - id: vllm
    service:
      commands:
        - python -m http.server 8000
      port: 8000
      resources:
        gpu: 16GB
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu: 0
""",
                "preset base must match legacy model",
            ),
            (
                "missing-recipes.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
""",
                "preset recipe must specify a service object",
            ),
            (
                "missing-service.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu: 0
""",
                "preset recipe must specify a service object",
            ),
            (
                "service-profile.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm
    service:
      commands:
        - python -m http.server 8000
      port: 8000
      resources:
        gpu: 16GB
      creation_policy: reuse
    validations:
      - replicas:
          - resources:
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
                "missing-service-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm
    service:
      commands:
        - python -m http.server 8000
      port: 8000
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu:
                  name: T4
                  memory: 16GB
                  count: 1
""",
                "preset service object must specify resources",
            ),
            (
                "group-missing-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm
    service:
      port: 8000
      replicas:
        - name: worker
          count: 1
          image: vllm/vllm-openai:latest
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu:
                  name: T4
                  memory: 16GB
                  count: 1
""",
                "preset service replica groups must specify resources",
            ),
            (
                "loose-resources.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: vllm
    service:
      commands:
        - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
      port: 8000
      resources:
        gpu: 16GB
    validations:
      - replicas:
          - resources:
              - gpu: 16GB
""",
                "preset validations must use exact replica resources",
            ),
            (
                "mismatched-validation-replicas.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: grouped
    service:
      port: 8000
      replicas:
        - name: router
          count: 1
          image: ghcr.io/example/router:latest
          resources:
            cpu: 4
        - name: worker
          count: 1
          image: vllm/vllm-openai:latest
          resources:
            gpu: 16GB
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu: 0
""",
                "preset validation replicas must match service replica group order",
            ),
            (
                "bad-replica-group-shape.yml",
                """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: grouped
    service:
      port: 8000
      replicas:
        - worker
    validations:
      - replicas:
          - resources:
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

        preset = build_endpoint_preset_from_run(run)
        variant_preset = build_endpoint_preset_from_run(
            run,
            recipe_model="groxaxo/Qwen3-4B-GPTQ-4Bit",
        )
        saved = await LocalDirEndpointPresetService(tmp_path).save_preset(PROJECT_NAME, preset)

        assert saved.base == "Qwen/Qwen3-4B"
        assert variant_preset.base == "Qwen/Qwen3-4B"
        assert variant_preset.recipes[0].model == "groxaxo/Qwen3-4B-GPTQ-4Bit"
        recipe = saved.recipes[0]
        assert recipe.model == "Qwen/Qwen3-4B"
        assert recipe.id == make_endpoint_preset_recipe_id(recipe.service)
        assert recipe.service.resources.gpu is not None
        assert recipe.service.resources.gpu.vendor is not None
        assert recipe.service.resources.gpu.vendor.value == "nvidia"
        assert "gpu=nvidia:16GB" in recipe.service.resources.pretty_format()
        resources = recipe.validations[0].replicas[0].resources[0].pretty_format()
        assert "cpu=14" in resources
        assert "gpu=L4:24GB:1" in resources

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
            build_endpoint_preset_from_run(run)

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

        preset = build_endpoint_preset_from_run(run)
        saved = await LocalDirEndpointPresetService(tmp_path).save_preset(PROJECT_NAME, preset)

        recipe = saved.recipes[0]
        assert [group.name for group in recipe.service.replica_groups] == [
            "router",
            "worker",
        ]
        assert "cpu=4" in recipe.service.replica_groups[0].resources.pretty_format()
        worker_resources = recipe.service.replica_groups[1].resources
        assert worker_resources.gpu is not None
        assert worker_resources.gpu.vendor is not None
        assert worker_resources.gpu.vendor.value == "nvidia"
        assert "gpu=nvidia:24GB" in worker_resources.pretty_format()
        assert len(recipe.validations[0].replicas[0].resources) == 1
        assert len(recipe.validations[0].replicas[1].resources) == 2


class TestBuildPresetServiceConfiguration:
    def test_get_endpoint_serving_run_name(self):
        assert get_endpoint_serving_run_name("qwen-endpoint") == "qwen-endpoint-serving"

    def test_get_endpoint_serving_run_name_keeps_long_name_to_avoid_truncation(self):
        endpoint_name = "a" * 41

        assert get_endpoint_serving_run_name(endpoint_name) == endpoint_name

    def test_endpoint_name_env_and_profile_are_applied(self):
        preset = _qwen_preset()
        recipe = preset.recipes[0]
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
            recipe=recipe,
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
        preset = _qwen_preset()
        recipe = preset.recipes[0]
        endpoint_configuration = EndpointConfiguration(
            name="endpoint-name",
            model="Qwen/Qwen3-4B",
        )

        run_spec = build_preset_run_spec(
            endpoint_name="endpoint-name",
            endpoint_configuration=endpoint_configuration,
            recipe=recipe,
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
        assert match.preset.base == "Qwen/Qwen3-4B"
        assert match.recipe.id == "vllm-t4"
        get_plan_mock.assert_awaited_once()
        assert get_plan_mock.await_args is not None
        assert get_plan_mock.await_args.kwargs["run_spec"].run_name == "qwen-endpoint-serving"

    @pytest.mark.asyncio
    async def test_exact_repo_request_skips_other_recipe_models(
        self, session: AsyncSession, tmp_path
    ):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        _write_qwen_preset_file(
            presets_dir / "qwen-a.yml",
            recipe_id="variant",
            recipe_model="groxaxo/Qwen3-4B-GPTQ-4Bit",
        )
        _write_qwen_preset_file(presets_dir / "qwen-b.yml", recipe_id="base")
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(return_value=_run_plan_with_offer(available=True)),
        ) as get_plan_mock:
            match = await find_matching_preset_plan(
                session=session,
                project=project,
                user=user,
                endpoint_name="qwen-endpoint",
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-endpoint",
                    model={"repo": "Qwen/Qwen3-4B"},
                ),
                preset_service=LocalDirEndpointPresetService(tmp_path),
            )

        assert match is not None
        assert match.recipe.id == "base"
        get_plan_mock.assert_awaited_once()

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
        assert result.unprovisionable.preset.base == "Qwen/Qwen3-4B"
        assert result.unprovisionable.recipe.id == "vllm-t4"

    @pytest.mark.asyncio
    async def test_uses_first_later_recipe_with_available_offers(
        self, session: AsyncSession, tmp_path
    ):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        _write_qwen_preset_file(presets_dir / "qwen-a.yml", recipe_id="vllm-t4", gpu="16GB")
        _write_qwen_preset_file(presets_dir / "qwen-b.yml", recipe_id="vllm-l4", gpu="24GB")
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(
                side_effect=[
                    _run_plan_with_offer(available=False),
                    _run_plan_with_offer(available=True),
                ]
            ),
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

        assert result.provisionable is not None
        assert result.provisionable.recipe.id == "vllm-l4"
        assert result.unprovisionable is not None
        assert result.unprovisionable.recipe.id == "vllm-t4"
        assert get_plan_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_stops_at_first_recipe_with_available_offers(
        self, session: AsyncSession, tmp_path
    ):
        presets_dir = _project_presets_dir(tmp_path)
        presets_dir.mkdir(parents=True)
        _write_qwen_preset_file(presets_dir / "qwen-a.yml", recipe_id="vllm-t4", gpu="16GB")
        _write_qwen_preset_file(presets_dir / "qwen-b.yml", recipe_id="vllm-l4", gpu="24GB")
        user = await create_user(
            session=session,
            global_role=GlobalRole.USER,
            ssh_public_key="ssh-rsa test",
        )
        project = await create_project(session=session, owner=user)

        with patch(
            "dstack._internal.server.services.endpoints.planning.runs_services.get_plan",
            new=AsyncMock(return_value=_run_plan_with_offer(available=True)),
        ) as get_plan_mock:
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
        assert match.recipe.id == "vllm-t4"
        get_plan_mock.assert_awaited_once()

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
recipes:
  - id: vllm-t4
    service:
      env:
        - HF_TOKEN
      commands:
        - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
      port: 8000
      resources:
        gpu: 16GB
    validations:
      - replicas:
          - resources:
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
    _write_qwen_preset_file(presets_dir / "qwen.yml")


def _write_qwen_preset_file(
    path,
    recipe_id: str = "vllm-t4",
    gpu: str = "16GB",
    recipe_model: str | None = None,
):
    recipe_model_line = f"    model: {recipe_model}\n" if recipe_model is not None else ""
    path.write_text(
        """\
type: endpoint-preset
model: Qwen/Qwen3-4B
recipes:
  - id: {recipe_id}
{recipe_model_line}\
    service:
      commands:
        - vllm serve Qwen/Qwen3-4B --host 0.0.0.0 --port 8000
      port: 8000
      resources:
        gpu: {gpu}
    validations:
      - replicas:
          - resources:
              - cpu: 4
                memory: 16GB
                disk: 100GB
                gpu:
                  name: T4
                  memory: 16GB
                  count: 1
""".format(recipe_id=recipe_id, gpu=gpu, recipe_model_line=recipe_model_line)
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


def _qwen_preset(
    recipe_id: str = "vllm-t4",
    resources: dict | None = None,
    recipe_model: str = "Qwen/Qwen3-4B",
) -> EndpointPreset:
    service = ServiceConfiguration.parse_obj(
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
            "resources": resources or {"gpu": "16GB"},
            "creation_policy": "reuse",
        }
    )
    return EndpointPreset(
        base="Qwen/Qwen3-4B",
        recipes=[
            EndpointPresetRecipe(
                id=recipe_id,
                model=recipe_model,
                service=service,
                validations=[
                    EndpointPresetValidation(
                        replicas=[
                            EndpointPresetValidationReplica.parse_obj(_t4_validation_replica())
                        ]
                    )
                ],
            )
        ],
    )


def _t4_validation_replica() -> dict:
    return {
        "resources": [
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
