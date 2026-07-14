from types import SimpleNamespace
from uuid import uuid4

from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoint_agent import AgentFinalReport
from dstack._internal.core.models.endpoint_presets import (
    EndpointBenchmark,
    EndpointBenchmarkClient,
    EndpointBenchmarkTarget,
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
)
from dstack._internal.core.models.instances import Disk, Gpu, Resources
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobStatus, Run, RunStatus, ServiceSpec


def get_endpoint_benchmark(*, verified: bool = True) -> EndpointBenchmark:
    benchmark = EndpointBenchmark(
        tool="vllm bench serve",
        tool_version="0.11.0",
        command="vllm bench serve --base-url $SERVICE_URL",
        workload={
            "api": "chat_completions",
            "num_requests": 16,
            "input_tokens": 1024,
            "output_tokens": 128,
            "concurrency": 1,
        },
        metrics={
            "successful_requests": 16,
            "failed_requests": 0,
            "duration_seconds": 48.64,
            "total_input_tokens": 16384,
            "total_output_tokens": 2048,
            "ttft_ms": {"mean": 110.9, "p50": 108.2, "p99": 121.6},
            "tpot_ms": {"mean": 7.5, "p50": 7.4, "p99": 8.1},
        },
    )
    if not verified:
        return benchmark
    return benchmark.copy(
        update={
            "target": EndpointBenchmarkTarget(type="server-proxy"),
            "client": EndpointBenchmarkClient(type="local"),
        }
    )


def get_endpoint_preset_recipe(
    *,
    recipe_id: str = "8f3a12c4",
    context_length: int = 32768,
) -> EndpointPresetRecipe:
    resources = ResourcesSpec.parse_obj(
        {
            "cpu": "16",
            "memory": "64GB",
            "disk": "200GB",
            "gpu": {"name": "A6000", "memory": "48GB", "count": 1},
        }
    )
    return EndpointPresetRecipe(
        base="Qwen/Qwen3.5-27B",
        id=recipe_id,
        model="community/Qwen3.5-27B-GPTQ-Int4",
        context_length=context_length,
        service=ServiceConfiguration.parse_obj(
            {
                "image": "vllm/vllm-openai:v0.11.0",
                "commands": ["vllm serve community/Qwen3.5-27B-GPTQ-Int4"],
                "port": 8000,
                "model": "Qwen/Qwen3.5-27B",
                "resources": {"gpu": "nvidia:40GB..48GB:1"},
                "env": ["HF_TOKEN"],
            }
        ),
        validations=[
            EndpointPresetValidation(
                replicas=[EndpointPresetValidationReplica(resources=[resources])],
                benchmark=get_endpoint_benchmark(),
            )
        ],
    )


def get_running_service_run() -> Run:
    service = ServiceConfiguration.parse_obj(
        {
            "name": "qwen-build-2",
            "image": "vllm/vllm-openai:v0.11.0",
            "commands": [
                "vllm serve community/Qwen3.5-27B-GPTQ-Int4 --served-model-name Qwen/Qwen3.5-27B"
            ],
            "port": 8000,
            "model": "Qwen/Qwen3.5-27B",
            "gateway": "benchmark-gateway",
            "fleets": ["gpu-fleet"],
            "backends": ["verda"],
            "spot_policy": "auto",
            "max_price": 0.5,
            "env": {"LICENSE": "license-secret", "TOKENIZERS_PARALLELISM": "false"},
            "resources": {"gpu": "40GB..48GB:1"},
        }
    )
    resources = Resources(
        cpus=16,
        memory_mib=64 * 1024,
        gpus=[Gpu(name="A6000", memory_mib=48 * 1024)],
        spot=False,
        disk=Disk(size_mib=200 * 1024),
    )
    job = SimpleNamespace(
        job_spec=SimpleNamespace(job_num=0, replica_num=0, replica_group="0"),
        job_submissions=[
            SimpleNamespace(
                deployment_num=0,
                status=JobStatus.RUNNING,
                job_runtime_data=SimpleNamespace(
                    offer=SimpleNamespace(instance=SimpleNamespace(resources=resources))
                ),
            )
        ],
    )
    return Run.construct(
        id=uuid4(),
        project_name="main",
        status=RunStatus.RUNNING,
        run_spec=SimpleNamespace(run_name="qwen-build-2", configuration=service),
        jobs=[job],
        service=ServiceSpec(url="/proxy/services/main/qwen-build-2/"),
        deployment_num=0,
    )


def get_successful_endpoint_report(run: Run) -> AgentFinalReport:
    return AgentFinalReport(
        success=True,
        run_id=run.id,
        run_name=run.run_spec.run_name,
        service_yaml="type: service",
        base="Qwen/Qwen3.5-27B",
        model="community/Qwen3.5-27B-GPTQ-Int4",
        context_length=32768,
        benchmark=get_endpoint_benchmark(verified=False),
    )
