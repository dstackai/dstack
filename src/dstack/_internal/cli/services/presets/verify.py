import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Optional, Sequence

from pydantic import BeforeValidator, ConfigDict, TypeAdapter, ValidationError, ValidationInfo

from dstack._internal.cli.models.preset_agent import (
    AnyPresetAgentResult,
    PresetAgentSuccess,
)
from dstack._internal.cli.models.presets import VerifiedPreset
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
from dstack._internal.core.models.configurations import PresetConfiguration, ServiceConfiguration
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.presets import (
    PresetBenchmark,
    PresetVerificationReplicaGroup,
    PresetWorkload,
)
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
    created_at: datetime,
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
        # The agent reports the served repo as `model`, the name the system
        # prompt has always used; the preset document calls it `repo`, so that
        # it cannot be confused with the service's client-facing model name.
        repo=report.model,
        context_length=report.context_length,
        benchmark=_normalized_benchmark(report.benchmark, preset_configuration),
        best_trial=report.trial,
        configuration=preset_configuration,
        preset_id=preset_id,
        created_at=created_at,
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


#: Characters that may follow the base name in a variant repo. A variant adds a
#: suffix — a quantisation, a format, a precision — and these are what separate
#: it, so requiring one stops ``Qwen3.5-27B`` from accepting ``Qwen3.5-27Bx``.
_VARIANT_SUFFIX_SEPARATORS = ("-", "_", ".")


def _model_name(repo: str) -> str:
    """The model half of a repo reference, without its owner.

    Deliberately owner-blind. A quantisation of a model is routinely published
    by someone other than the original author — this repository's own fixtures
    pair a ``Qwen/Qwen3.5-27B`` base with a ``community/Qwen3.5-27B-GPTQ-Int4``
    repo — so requiring the owner to match would reject the ordinary case.
    """
    return repo.rsplit("/", 1)[-1].strip()


def _is_variant_of(repo: str, base: str) -> bool:
    """Is ``repo`` a variant of ``base``, rather than a different model?

    A variant is the base plus a suffix: ``Qwen3.5-27B`` also answers to
    ``Qwen3.5-27B-GPTQ-Int4`` and ``Qwen3.5-27B-AWQ``. A different generation
    is not a variant, however similar the name — ``Qwen3.8-27B`` does not
    answer a request for ``Qwen3.5-27B``, which is exactly the substitution
    that verified clean before.

    Compared case-insensitively, and on the model name alone, so the check
    stays about which model was served rather than about who published it.
    """
    served = _model_name(repo).lower()
    wanted = _model_name(base).lower()
    if not served or not wanted:
        return False
    if served == wanted:
        return True
    if not served.startswith(wanted):
        return False
    return served[len(wanted)] in _VARIANT_SUFFIX_SEPARATORS


def _check_report_answers_request(
    report: PresetAgentSuccess, configuration: PresetConfiguration
) -> None:
    """The report must answer what the configuration asked: the same benchmark
    workload, and the requested model — exactly when it was exact, any variant of
    the base otherwise."""
    _check_workload_answers_request(report.benchmark.workload, configuration)
    if configuration.model.allows_variant_selection:
        if report.base != configuration.model.api_model_name:
            raise CLIError("Claude final report base does not match the requested model")
        # The base must constrain which repos are acceptable, and echoing it
        # back does not: the served repo is what the agent chose, and it was
        # only ever checked against the *advertised* name — which a
        # substitution preserves. `vllm serve Qwen/Qwen3.5-27B-GPTQ-Int4
        # --served-model-name Qwen/Qwen3.8-27B` answered a request for
        # Qwen3.8 with a different model generation and verified clean.
        if not _is_variant_of(report.model, configuration.model.api_model_name):
            raise CLIError(
                f"Claude served {report.model!r}, which is not a variant of the requested"
                f" base {configuration.model.api_model_name!r}"
            )
    elif report.model != configuration.model.exact_repo:
        raise CLIError("Claude changed an exact model request")


def _check_workload_answers_request(
    workload: PresetWorkload, configuration: PresetConfiguration
) -> None:
    """Only what the configuration specifies exactly is compared. A named dataset is
    compared by name, because the request and the report both use the dataset's own
    name. A synthetic workload has no such shared name — the report's `dataset`, if
    any, is the benchmark tool's own name for the data it generated — so the shared
    prefix it was run with is compared instead. `input_tokens` and `output_tokens`
    are what the benchmark measured rather than an echo of the request, so they are
    not compared."""
    if configuration.dataset is not None:
        if workload.dataset != configuration.dataset:
            raise CLIError(
                f"Claude final benchmark dataset {workload.dataset!r} does not match the"
                f" requested dataset {configuration.dataset!r}"
            )
    else:
        shared_prefix_tokens = configuration.shared_prefix_tokens or 0
        if workload.shared_prefix_tokens != shared_prefix_tokens:
            raise CLIError(
                f"Claude final benchmark shared prefix of {workload.shared_prefix_tokens}"
                f" tokens does not match the requested {shared_prefix_tokens}"
            )
    if configuration.concurrency is not None and workload.concurrency != configuration.concurrency:
        raise CLIError(
            f"Claude final benchmark concurrency of {workload.concurrency} does not match the"
            f" requested concurrency of {configuration.concurrency}"
        )


def _normalized_benchmark(
    benchmark: PresetBenchmark, configuration: PresetConfiguration
) -> PresetBenchmark:
    """The stored workload states the request, and the configuration is the
    authority on what was requested: a synthetic run carries no dataset — whatever
    the benchmark tool called its generated data is already on record in `command`
    — and a dataset run carries no shared prefix. The agent's report may volunteer
    either; neither is trusted into the record."""
    workload = benchmark.workload.model_copy(
        update=(
            {"dataset": None} if configuration.dataset is None else {"shared_prefix_tokens": 0}
        )
    )
    return benchmark.model_copy(update={"workload": workload})


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
