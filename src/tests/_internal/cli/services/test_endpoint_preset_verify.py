import pytest

from dstack._internal.cli.services.endpoint_preset_verify import (
    build_verified_endpoint_preset,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.profiles import ProfileParams
from tests._internal.cli.endpoint_presets import (
    get_endpoint_benchmark,
    get_running_service_run,
    get_successful_endpoint_report,
)

pytestmark = pytest.mark.windows


class TestBuildVerifiedEndpointPreset:
    def test_builds_portable_self_contained_recipe(self):
        run = get_running_service_run()

        recipe = build_verified_endpoint_preset(
            run=run,
            endpoint_configuration=EndpointConfiguration(
                name="qwen-build",
                model={"base": "Qwen/Qwen3.5-27B"},
                context_length=8192,
                gateway="benchmark-gateway",
                env={"LICENSE": "license-secret"},
            ),
            report=get_successful_endpoint_report(run),
            benchmarks=[get_endpoint_benchmark(run_id=run.id, run_name=run.run_spec.run_name)],
        )

        assert recipe.base == "Qwen/Qwen3.5-27B"
        assert recipe.model == "community/Qwen3.5-27B-GPTQ-Int4"
        assert recipe.context_length == 32768
        assert recipe.service.name is None
        assert recipe.service.gateway is None
        assert all(getattr(recipe.service, field) is None for field in ProfileParams.__fields__)
        assert isinstance(recipe.service.env["LICENSE"], EnvSentinel)
        assert recipe.service.resources.gpu.vendor.value == "nvidia"
        validation = recipe.validations[0]
        assert validation.replicas[0].resources[0].gpu.name == ["A6000"]
        assert validation.benchmarks[0].target.type == "server-proxy"
        assert validation.benchmarks[0].client.type == "local"

    def test_rejects_variant_for_exact_model_request(self):
        run = get_running_service_run()
        report = get_successful_endpoint_report(run).copy(update={"model": "other/model"})

        with pytest.raises(CLIError, match="changed an exact model request"):
            build_verified_endpoint_preset(
                run=run,
                endpoint_configuration=EndpointConfiguration(
                    name="qwen-build",
                    model={
                        "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                        "name": "Qwen/Qwen3.5-27B",
                    },
                ),
                report=report,
                benchmarks=[get_endpoint_benchmark(run_id=run.id, run_name=run.run_spec.run_name)],
            )
