import pytest

from dstack._internal.core.models.configurations import (
    DEFAULT_MODEL_PROBE_TIMEOUT,
    DEFAULT_MODEL_PROBE_URL,
    ProbeConfig,
    ServiceConfiguration,
)
from dstack._internal.core.models.services import OpenAIChatModel
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
        assert probe.url == DEFAULT_MODEL_PROBE_URL
        assert probe.timeout == DEFAULT_MODEL_PROBE_TIMEOUT
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
