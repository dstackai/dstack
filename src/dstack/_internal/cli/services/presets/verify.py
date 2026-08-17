import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional, Sequence

from pydantic import BeforeValidator, ConfigDict, TypeAdapter, ValidationError, ValidationInfo

from dstack._internal.cli.models.configurations import PresetConfiguration
from dstack._internal.cli.models.preset_agent import (
    AnyPresetAgentResult,
    PresetAgentSuccess,
)
from dstack._internal.cli.models.presets import (
    PresetVerificationReplicaGroup,
    VerifiedPreset,
)
from dstack._internal.cli.services.presets.agent import (
    PresetAgentProcessOutput,
)
from dstack._internal.cli.services.presets.build import (
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


def _prepare_report(value: Any, info: ValidationInfo) -> Any:
    """The parse itself redacts, so an unredacted report cannot be parsed at all —
    the redaction cannot be forgotten at a call site. Explicit nulls are dropped
    because the wire schema cannot forbid them on either outcome's fields."""
    if info.context is None or "redacted_values" not in info.context:
        raise ValueError("an agent report must be parsed with redacted_values in context")
    value = redact_structure(value, info.context["redacted_values"])
    if isinstance(value, dict):
        value = {key: item for key, item in value.items() if item is not None}
    return value


# Input hiding is defense in depth: it keeps credentials that redaction did not
# know about out of the error text shown to the user.
_AGENT_RESULT_ADAPTER = TypeAdapter(
    Annotated[AnyPresetAgentResult, BeforeValidator(_prepare_report)],
    config=ConfigDict(hide_input_in_errors=True),
)


def load_preset_agent_report(
    *,
    output: PresetAgentProcessOutput,
    workspace: PresetAgentWorkspace,
    redacted_values: Sequence[str],
) -> AnyPresetAgentResult:
    """The agent's outcome, success or failure, with its secrets redacted.
    Raises only when there is no valid report at all."""
    report_data = output.report_data or _load_json_object(workspace.final_report_path)
    if report_data is None:
        raise CLIError(
            redact(
                output.error or "Claude exited without a final report",
                redacted_values,
            )
        )
    try:
        return _AGENT_RESULT_ADAPTER.validate_python(
            report_data, context={"redacted_values": tuple(redacted_values)}
        )
    except ValidationError as e:
        raise CLIError(f"Claude returned an invalid final report: {e}") from e


def build_verified_preset(
    *,
    run: Run,
    preset_configuration: PresetConfiguration,
    report: PresetAgentSuccess,
    workspace_path: Path,
    session_path: Path,
    preset_id: str,
    name: Optional[str],
    submitted_at: datetime,
) -> VerifiedPreset:
    """Cross-checks the agent's self-reported final report against the actual run
    and service state before trusting it to build a preset. The preset's service is
    taken from the run the server verified, not from anything the agent wrote, and
    is then stripped of this machine's deployment choices; the session keeps the
    agent's own files verbatim as the record of what ran."""
    service = _verified_run_service(run, report)
    _check_report_answers_request(report, preset_configuration)
    if service.model is None or service.model.name != preset_configuration.model.api_model_name:
        raise CLIError("Claude final service model name does not match the requested model")
    return build_preset(
        name=name,
        service=_portable_service(
            service,
            preset_configuration,
            workspace_path=workspace_path,
            session_path=session_path,
        ),
        verification_replica_groups=_get_verification_replica_groups(run, service),
        base_model=report.base,
        model=report.model,
        context_length=report.context_length,
        benchmark=report.benchmark,
        best_trial=report.trial,
        configuration=preset_configuration,
        preset_id=preset_id,
        submitted_at=submitted_at,
    )


def _verified_run_service(run: Run, report: PresetAgentSuccess) -> ServiceConfiguration:
    """The service the server actually runs, after proving the report talks about
    this run and the run is a live model service."""
    if run.id != report.run_id or run.run_spec.run_name != report.run_name:
        raise CLIError("Claude final report identifies a different service run")
    if run.status != RunStatus.RUNNING or run.service is None:
        raise CLIError("Claude final service is not running")
    service = run.run_spec.configuration
    if not isinstance(service, ServiceConfiguration):
        raise CLIError("Claude final run is not a model service")
    return service


def _check_report_answers_request(
    report: PresetAgentSuccess, configuration: PresetConfiguration
) -> None:
    """The report must answer what the configuration asked: the same dataset, and
    the requested model — exactly when it was exact, any variant of the base
    otherwise."""
    if report.benchmark.workload.dataset != configuration.effective_dataset:
        raise CLIError("Claude final benchmark dataset does not match the requested dataset")
    if configuration.model.allows_variant_selection:
        if report.base != configuration.model.api_model_name:
            raise CLIError("Claude final report base does not match the requested model")
    elif report.model != configuration.model.exact_repo:
        raise CLIError("Claude changed an exact model request")


def _portable_service(
    service: ServiceConfiguration,
    configuration: PresetConfiguration,
    *,
    workspace_path: Path,
    session_path: Path,
) -> ServiceConfiguration:
    """The service as the preset carries it: env values become the references the
    user wrote, and workspace file paths are re-rooted onto the session's mirrored
    copies, because the submission workspace is deleted when the session ends."""
    portable = service.model_copy(deep=True)
    for key, value in configuration.env.items():
        if isinstance(value, EnvSentinel) and key in portable.env:
            portable.env[key] = value
    for mapping in portable.files:
        mapping.local_path = _mirrored_file_path(
            mapping.local_path, workspace_path=workspace_path, session_path=session_path
        )
    return portable


def _mirrored_file_path(local_path: str, *, workspace_path: Path, session_path: Path) -> str:
    """The path relative to the preset directory (the store resolves it at load),
    proven to have a mirrored copy: only `trials/` and `service/` are mirrored."""
    try:
        relative = Path(local_path).resolve().relative_to(workspace_path.resolve())
    except ValueError:
        raise CLIError(f"Claude final service file '{local_path}' is outside the agent workspace")
    if (
        relative.parts[:1] not in (("trials",), ("service",))
        or not (session_path / relative).exists()
    ):
        raise CLIError(
            f"Claude final service file '{local_path}' has no mirrored copy"
            f" at '{session_path / relative}'"
        )
    return relative.as_posix()


def _get_verification_replica_groups(
    run: Run,
    service: ServiceConfiguration,
) -> list[PresetVerificationReplicaGroup]:
    groups: list[PresetVerificationReplicaGroup] = []
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
        groups.append(PresetVerificationReplicaGroup(name=group.name, replicas=resources))
    return groups


def _load_json_object(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
