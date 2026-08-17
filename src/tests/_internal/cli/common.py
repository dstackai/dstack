import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import IO, Any, List, Optional
from unittest.mock import patch
from uuid import uuid4

from rich.console import Console
from rich.theme import Theme

from dstack._internal.cli.main import main
from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.preset_agent import (
    PresetAgentSuccess,
    PresetSessionFinalize,
    PresetSessionRun,
    PresetSessionState,
    PresetSessionWorkspace,
)
from dstack._internal.cli.models.presets import (
    PresetBenchmark,
    PresetVerificationReplicaGroup,
    VerifiedPreset,
)
from dstack._internal.compat import IS_WINDOWS
from dstack._internal.core.models.configurations import (
    DEFAULT_REPLICA_GROUP_NAME,
    ServiceConfiguration,
)
from dstack._internal.core.models.instances import Disk, Gpu, Resources
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobStatus, Run, RunStatus, ServiceSpec


def plain_console(file: IO[str], *, width: int = 250) -> Console:
    """A plain-text console for asserting on CLI table output."""
    return Console(
        file=file,
        width=width,
        color_system=None,
        theme=Theme({"secondary": "grey58"}),
    )


def run_dstack_cli(
    cli_args: List[str],
    home_dir: Optional[Path] = None,
    repo_dir: Optional[Path] = None,
) -> int:
    exit_code = 0
    if repo_dir is not None:
        cwd = os.getcwd()
        os.chdir(repo_dir)
    if home_dir is not None:
        prev_home_dir = os.environ.get("HOME")
        os.environ["HOME"] = str(home_dir)
        if IS_WINDOWS:
            prev_userprofile = os.environ.get("USERPROFILE")
            os.environ["USERPROFILE"] = str(home_dir)
    with patch("sys.argv", ["dstack"] + cli_args):
        try:
            main()
        except SystemExit as e:
            exit_code = e.code
        finally:
            if home_dir is not None:
                if prev_home_dir is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = prev_home_dir
                if IS_WINDOWS:
                    if prev_userprofile is None:
                        os.environ.pop("USERPROFILE", None)
                    else:
                        os.environ["USERPROFILE"] = prev_userprofile
            if repo_dir is not None:
                os.chdir(cwd)
    return exit_code


def get_preset_benchmark() -> PresetBenchmark:
    benchmark = PresetBenchmark(
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
            "output_tok_per_s": 42.1,
            "per_user_tok_per_s": 42.1,
            "ttft_ms": {"mean": 110.9, "p50": 108.2, "p99": 121.6},
            "tpot_ms": {"mean": 7.5, "p50": 7.4, "p99": 8.1},
        },
    )
    return benchmark


def get_preset(
    *,
    preset_id: str = "8f3a12c4",
    context_length: int = 32768,
) -> VerifiedPreset:
    resources = ResourcesSpec.model_validate(
        {
            "cpu": "16",
            "memory": "64GB",
            "disk": "200GB",
            "gpu": {"name": "A6000", "memory": "48GB", "count": 1},
        }
    )
    return VerifiedPreset(
        configuration=PresetConfiguration.model_validate(
            {
                "type": "preset",
                "base": "Qwen/Qwen3.5-27B",
                "trials": 3,
                "concurrency": 1,
                "input_tokens": 1024,
                "output_tokens": 128,
            }
        ),
        base="Qwen/Qwen3.5-27B",
        id=preset_id,
        model="community/Qwen3.5-27B-GPTQ-Int4",
        submitted_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        service=ServiceConfiguration.model_validate(
            {
                "image": "vllm/vllm-openai:v0.11.0",
                "commands": ["vllm serve community/Qwen3.5-27B-GPTQ-Int4"],
                "port": 8000,
                "model": "Qwen/Qwen3.5-27B",
                "resources": {"gpu": "nvidia:40GB..48GB:1"},
                "env": ["HF_TOKEN"],
            }
        ),
        context_length=context_length,
        best_trial=1,
        benchmark=get_preset_benchmark(),
        verified_on=[
            PresetVerificationReplicaGroup(name=DEFAULT_REPLICA_GROUP_NAME, replicas=[resources])
        ],
    )


def get_running_service_run() -> Run:
    service = ServiceConfiguration.model_validate(
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
    return Run.model_construct(
        id=uuid4(),
        project_name="main",
        status=RunStatus.RUNNING,
        run_spec=SimpleNamespace(run_name="qwen-build-2", configuration=service),
        jobs=[job],
        service=ServiceSpec(url="/proxy/services/main/qwen-build-2/"),
        deployment_num=0,
    )


def get_session_state(**overrides: Any) -> PresetSessionState:
    fields: dict[str, Any] = {
        "id": "ab12cd34",
        "name": None,
        "model": "Qwen/Qwen3.5-27B",
        "trials_num": None,
        "previous": [],
        "created_at": datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        "debug": False,
        "status": "running",
        "owner": None,
        "run": None,
    }
    fields.update(overrides)
    return PresetSessionState(**fields)


def get_session_run(**overrides: Any) -> PresetSessionRun:
    fields: dict[str, Any] = {
        "workspace": PresetSessionWorkspace(path="/tmp/preset-ws", alias="/tmp/preset-ws"),
        "finalize": PresetSessionFinalize(project="main", keep_service=False),
        "claude_model": None,
        "agent": None,
        "claude_session_id": None,
    }
    fields.update(overrides)
    return PresetSessionRun(**fields)


def get_successful_preset_report(run: Run) -> PresetAgentSuccess:
    return PresetAgentSuccess(
        success=True,
        run_id=run.id,
        run_name=run.run_spec.run_name,
        service_yaml="type: service",
        trial=1,
        base="Qwen/Qwen3.5-27B",
        model="community/Qwen3.5-27B-GPTQ-Int4",
        context_length=32768,
        benchmark=get_preset_benchmark(),
    )
