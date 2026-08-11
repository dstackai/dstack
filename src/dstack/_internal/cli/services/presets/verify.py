import json
from pathlib import Path
from typing import Any, Optional, Sequence
from urllib.parse import urlparse

from pydantic import ValidationError

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.preset_agent import AgentFinalReport
from dstack._internal.cli.models.presets import (
    Preset,
    PresetBenchmarkClient,
    PresetBenchmarkTarget,
    PresetValidationReplica,
)
from dstack._internal.cli.services.presets.agent import (
    PresetAgentProcessOutput,
)
from dstack._internal.cli.services.presets.presets import (
    build_preset,
    resources_spec_from_instance_resources,
)
from dstack._internal.cli.services.presets.redaction import (
    redact,
    redact_structure,
)
from dstack._internal.cli.services.presets.workspace import (
    PresetAgentWorkspace,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.runs import JobStatus, Run, RunStatus


def load_preset_agent_report(
    *,
    output: PresetAgentProcessOutput,
    workspace: PresetAgentWorkspace,
    redacted_values: Sequence[str],
) -> AgentFinalReport:
    report_data = output.report_data or _load_json_object(workspace.final_report_path)
    if report_data is None:
        raise CLIError(
            redact(
                output.error or "Claude exited without a final report",
                redacted_values,
            )
        )
    # Redact known secrets; an unknown leaked token is still caught downstream by
    # the command bearer-token check.
    report_data = redact_structure(report_data, redacted_values)
    try:
        report = AgentFinalReport.model_validate(report_data)
    except ValidationError as e:
        raise CLIError(f"Claude returned an invalid final report: {e}") from e
    if not report.success:
        raise CLIError(
            redact(
                report.failure_summary or "Claude did not create a preset",
                redacted_values,
            )
        )
    return report


def _rewrite_workspace_file_paths(
    service: ServiceConfiguration, *, workspace_path: Path, session_path: Path
) -> None:
    """Re-roots `files` onto the session's mirrored copies because the submission
    workspace is deleted when the session ends; only `trials/` and `service/` are mirrored."""
    workspace_root = workspace_path.resolve()
    for mapping in service.files:
        try:
            relative = Path(mapping.local_path).resolve().relative_to(workspace_root)
        except ValueError:
            raise CLIError(
                f"Claude final service file '{mapping.local_path}' is outside the agent workspace"
            )
        target = session_path / relative
        if relative.parts[:1] not in (("trials",), ("service",)) or not target.exists():
            raise CLIError(
                f"Claude final service file '{mapping.local_path}' has no mirrored copy"
                f" at '{target}'"
            )
        mapping.local_path = str(target)


def build_verified_preset(
    *,
    run: Run,
    preset_configuration: PresetConfiguration,
    report: AgentFinalReport,
    workspace_path: Optional[Path] = None,
    session_path: Optional[Path] = None,
    preset_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Preset:
    """Cross-checks the agent's self-reported final report against the actual run
    and service state before trusting it to build a preset."""
    if run.id != report.run_id or run.run_spec.run_name != report.run_name:
        raise CLIError("Claude final report identifies a different service run")
    if run.status != RunStatus.RUNNING or run.service is None:
        raise CLIError("Claude final service is not running")
    service = run.run_spec.configuration
    if not isinstance(service, ServiceConfiguration) or service.model is None:
        raise CLIError("Claude final run is not a model service")
    if service.model.name != preset_configuration.model.api_model_name:
        raise CLIError("Claude final service model name does not match the requested model")
    assert report.base is not None
    assert report.model is not None
    assert report.context_length is not None
    assert report.benchmark is not None
    if preset_configuration.model.allows_variant_selection:
        if report.base != preset_configuration.model.api_model_name:
            raise CLIError("Claude final report base does not match the requested model")
    elif report.model != preset_configuration.model.exact_repo:
        raise CLIError("Claude changed an exact model request")

    target_type = (
        "gateway" if urlparse(run.service.url).scheme in {"http", "https"} else "server-proxy"
    )
    benchmark = report.benchmark.model_copy(
        update={
            "target": PresetBenchmarkTarget(type=target_type),
            "client": PresetBenchmarkClient(type="local"),
        }
    )
    portable_service = service.model_copy(deep=True)
    # The CLI resolved preset env references before submission; presets retain the references.
    for key, value in preset_configuration.env.items():
        if isinstance(value, EnvSentinel) and key in portable_service.env:
            portable_service.env[key] = value
    if portable_service.files:
        if workspace_path is None or session_path is None:
            raise CLIError("Claude final service uses files but no workspace is attached")
        _rewrite_workspace_file_paths(
            portable_service, workspace_path=workspace_path, session_path=session_path
        )
    return build_preset(
        name=name,
        service=portable_service,
        validation_replicas=_get_validation_replicas(run, service),
        base_model=report.base,
        model=report.model,
        context_length=report.context_length,
        benchmark=benchmark,
        trial=report.trial,
        min_context_length=preset_configuration.min_context_length,
        max_ttft=preset_configuration.max_ttft,
        preset_id=preset_id,
    )


def _get_validation_replicas(
    run: Run,
    service: ServiceConfiguration,
) -> list[PresetValidationReplica]:
    replicas: list[PresetValidationReplica] = []
    for group in service.replica_groups:
        resources = []
        for job in sorted(run.jobs, key=lambda job: job.job_spec.replica_num):
            if job.job_spec.job_num != 0 or job.job_spec.replica_group != group.name:
                continue
            submissions = [
                submission
                for submission in job.job_submissions
                if submission.deployment_num == run.deployment_num
                and submission.status == JobStatus.RUNNING
            ]
            if not submissions:
                continue
            runtime_data = submissions[-1].job_runtime_data
            if runtime_data is None or runtime_data.offer is None:
                raise CLIError("Final service run does not expose actual instance resources")
            resources.append(
                resources_spec_from_instance_resources(runtime_data.offer.instance.resources)
            )
        if not resources:
            raise CLIError(f"Final service replica group {group.name!r} has no running replicas")
        replicas.append(PresetValidationReplica(resources=resources))
    return replicas


def _load_json_object(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
