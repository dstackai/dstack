from unittest.mock import Mock

import pytest

from dstack._internal import settings
from dstack._internal.core.models.configurations import (
    OPENAI_MODEL_PROBE_TIMEOUT,
    ProbeConfig,
    PythonVersion,
    ReplicaGroup,
    ServiceConfiguration,
)
from dstack._internal.core.models.resources import Range
from dstack._internal.core.models.services import OpenAIChatModel
from dstack._internal.server.services.docker import ImageConfig
from dstack._internal.server.services.jobs.configurators.base import get_default_image
from dstack._internal.server.services.jobs.configurators.service import ServiceJobConfigurator
from dstack._internal.server.testing.common import get_run_spec


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
class TestProbes:
    async def test_default_probe_when_model_set(self):
        """When model is set but probes omitted, a default model probe should be generated."""
        configuration = ServiceConfiguration(
            port=80,
            image="debian",
            model=OpenAIChatModel(
                name="meta-llama/Meta-Llama-3.1-8B-Instruct",
                format="openai",
            ),
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = ServiceJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 1
        probes = job_specs[0].probes
        assert len(probes) == 1
        probe = probes[0]
        assert probe.type == "http"
        assert probe.method == "post"
        assert probe.url == "/v1/chat/completions"
        assert probe.timeout == OPENAI_MODEL_PROBE_TIMEOUT
        assert len(probe.headers) == 1
        assert probe.headers[0].name == "Content-Type"
        assert probe.headers[0].value == "application/json"
        assert "meta-llama/Meta-Llama-3.1-8B-Instruct" in (probe.body or "")
        assert "max_tokens" in (probe.body or "")

    async def test_explicit_probes_not_overridden(self):
        """When probes are explicitly set, they should be used as-is."""
        configuration = ServiceConfiguration(
            port=80,
            image="debian",
            model=OpenAIChatModel(
                name="meta-llama/Meta-Llama-3.1-8B-Instruct",
                format="openai",
            ),
            probes=[ProbeConfig(type="http", url="/health")],
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = ServiceJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 1
        probes = job_specs[0].probes
        assert len(probes) == 1
        assert probes[0].url == "/health"

    async def test_explicit_empty_probes(self):
        """When probes is explicitly set to empty list, no probes should be generated."""
        configuration = ServiceConfiguration(
            port=80,
            image="debian",
            model=OpenAIChatModel(
                name="meta-llama/Meta-Llama-3.1-8B-Instruct",
                format="openai",
            ),
            probes=[],
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = ServiceJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 1
        assert len(job_specs[0].probes) == 0

    async def test_no_probe_when_no_model(self):
        """When neither model nor probes are set, no probes should be generated."""
        configuration = ServiceConfiguration(
            port=80,
            image="debian",
        )
        run_spec = get_run_spec(run_name="run", repo_id="id", configuration=configuration)
        configurator = ServiceJobConfigurator(run_spec)

        job_specs = await configurator.get_job_specs(replica_num=0)

        assert len(job_specs) == 1
        assert len(job_specs[0].probes) == 0


def _make_run_spec(replicas, **service_kwargs):
    configuration = ServiceConfiguration(
        port=80,
        replicas=replicas,
        **service_kwargs,
    )
    return get_run_spec(run_name="run", repo_id="id", configuration=configuration)


@pytest.mark.asyncio
@pytest.mark.usefixtures("image_config_mock")
class TestPerGroupOverrides:
    """Verifies that ServiceJobConfigurator picks up per-replica-group
    image-source fields (image, docker, python, nvcc, privileged)."""

    async def test_image_name_uses_group_image(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    image="custom:1.0",
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._image_name() == "custom:1.0"

    async def test_image_name_uses_dind_when_group_docker_true(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    docker=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._image_name() == settings.DSTACK_DIND_IMAGE

    async def test_image_name_uses_nvcc_default_when_group_nvcc_true(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    nvcc=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._image_name() == get_default_image(nvcc=True)

    async def test_image_name_falls_back_to_service_image(self):
        run_spec = _make_run_spec(
            image="svc:1.0",
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._image_name() == "svc:1.0"

    async def test_privileged_true_when_group_docker(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    docker=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._privileged() is True

    async def test_privileged_returns_group_privileged(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    image="x",
                    privileged=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._privileged() is True

    async def test_privileged_defers_to_super_when_group_unset(self):
        run_spec = _make_run_spec(
            image="svc:1.0",
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        # Service-level privileged defaults to False
        assert configurator._privileged() is False

    async def test_dstack_image_commands_injects_start_dockerd_for_docker(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    docker=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._dstack_image_commands() == ["start-dockerd"]

    async def test_dstack_image_commands_empty_for_group_image(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    image="alpine",
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._dstack_image_commands() == []

    async def test_shell_bash_when_group_docker(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    docker=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._shell() == "/bin/bash"

    async def test_shell_sh_when_group_image(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    image="alpine",
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._shell() == "/bin/sh"

    async def test_python_uses_group_python(self):
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    python=PythonVersion.PY312,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        assert configurator._python() == "3.12"

    async def test_user_looks_up_group_image(self, monkeypatch: pytest.MonkeyPatch):
        """When a group sets its own `image`, _user() queries that image's config."""
        image_config = ImageConfig.parse_obj({"User": "nginx", "Entrypoint": None, "Cmd": []})
        monkeypatch.setattr(
            "dstack._internal.server.services.jobs.configurators.base._get_image_config",
            Mock(return_value=image_config),
        )
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    image="nginxinc/nginx-unprivileged",
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        user = await configurator._user()
        assert user is not None

    async def test_user_does_not_lookup_for_group_docker(self, monkeypatch: pytest.MonkeyPatch):
        """`docker: true` should not trigger an image-config registry call."""
        mock_get_image_config = Mock()
        monkeypatch.setattr(
            "dstack._internal.server.services.jobs.configurators.base._get_image_config",
            mock_get_image_config,
        )
        run_spec = _make_run_spec(
            replicas=[
                ReplicaGroup(
                    name="a",
                    count=Range(min=1, max=1),
                    docker=True,
                    commands=["x"],
                )
            ],
        )
        configurator = ServiceJobConfigurator(run_spec, replica_group_name="a")
        await configurator._user()
        mock_get_image_config.assert_not_called()
