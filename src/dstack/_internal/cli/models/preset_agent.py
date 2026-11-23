import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, Literal, Optional, Self, Union

import yaml
from pydantic import (
    Field,
    PositiveInt,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
    model_validator,
)

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import PresetAgentProvider, ServiceConfiguration
from dstack._internal.core.models.presets import PresetBenchmark, PresetResult


class PresetAgentInvalidService(CoreModel):
    """A reported service YAML that does not parse; the reason, not a failure."""

    raw: str
    error: str


def _service_from_yaml(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
    if not isinstance(value, str):
        return handler(value)
    try:
        return ServiceConfiguration.model_validate(yaml.safe_load(value))
    except ValidationError as e:
        return PresetAgentInvalidService(raw=value, error=e.errors()[0]["msg"])
    except yaml.YAMLError as e:
        return PresetAgentInvalidService(raw=value, error=str(e))


# The agent writes YAML text; the parse yields the service or the typed reason
# it is not one. The schema keeps telling the agent `string`.
ReportedService = Annotated[
    Union[ServiceConfiguration, PresetAgentInvalidService],
    WrapValidator(_service_from_yaml, json_schema_input_type=str),
]


class PresetAgentSuccess(CoreModel):
    """A preset the agent created, cross-checked against the run in `verify`."""

    success: Literal[True]
    run_id: uuid.UUID
    run_name: str
    service_yaml: ReportedService
    trial: PositiveInt
    base: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    result: Annotated[list[PresetResult], Field(min_length=1)]


class PresetAgentFailure(CoreModel):
    """Why the agent created no preset."""

    success: Literal[False]
    failure_summary: str


AnyPresetAgentResult = Union[PresetAgentSuccess, PresetAgentFailure]


class PresetTrialBenchmark(PresetBenchmark):
    """A trial's benchmark, which the agent writes into `trials/<n>/trial.json`
    after benchmarking the trial at a concurrency, read by the CLI for
    `dstack preset list`. `PresetBenchmark.validate_metrics` is overridden
    because its rule is for the final report; applied to `trial.json` it would
    drop the whole trial from the listing."""

    @model_validator(mode="after")
    def validate_metrics(self) -> Self:
        return self


class PresetTrialResult(CoreModel):
    """One `result` entry of `trials/<n>/trial.json`, as the system prompt
    defines it: the agent writes one per concurrency in `constraints.json` once
    the trial is benchmarked, and the CLI reads them for `dstack preset list`.
    The entry's `learned` field is left out: the CLI does not use it, because
    the agent writes it for its own reading in later sessions."""

    concurrency: Optional[PositiveInt] = None
    context_length: Optional[PositiveInt] = None
    benchmark: Optional[PresetTrialBenchmark] = None
    failed: bool = False

    @model_validator(mode="after")
    def fail_without_benchmark(self) -> Self:
        """An entry without a benchmark is one the agent could not measure, which
        the prompt defines as failed; the flag is set in case the agent left it out."""
        if self.benchmark is None:
            self.failed = True
        return self


def _entry_or_failed(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
    try:
        return handler(value)
    except ValidationError:
        # A broken entry counts as a failed one, so the other entries of the
        # trial are still listed.
        return PresetTrialResult(failed=True)


class PresetTrial(CoreModel):
    """The `trials/<n>/trial.json` record as defined in the system_prompt.md.
    The agent writes it once trial `<n>` is benchmarked, and its presence is
    what marks the trial completed; the CLI reads it for `dstack preset list`."""

    resources: Optional[dict[str, Any]] = None
    groups: Optional[list[list[dict[str, Any]]]] = None
    # Required and non-empty: `system_prompt.md` states that `trial.json` has
    # one `result` entry per concurrency value.
    result: Annotated[
        list[Annotated[PresetTrialResult, WrapValidator(_entry_or_failed)]],
        Field(min_length=1),
    ]

    @model_validator(mode="before")
    @classmethod
    def convert_to_result_list(cls, data: Any) -> Any:
        # An old `trial.json` has no `result` list. Its `benchmark`,
        # `context_length` and `failed` are at the top level, and a failed one
        # may have no `benchmark` at all.
        if isinstance(data, dict) and "result" not in data:
            data = dict(data)
            data["result"] = [
                {
                    key: data.pop(key)
                    for key in ("benchmark", "context_length", "failed")
                    if key in data
                }
            ]
        return data


PresetSessionStatus = Literal["running", "interrupted", "success", "failed"]

# The session models carry no defaults: `session.json` is this CLI's own state
# file, so every write states the whole state, and a `null` in the file is a
# statement (a detached session has `owner: null`), not an omission.


class PresetSessionProcess(CoreModel):
    pid: int
    # The start time guards against pid reuse; psutil may fail to provide it.
    started_at: Optional[float]


class PresetSessionWorkspace(CoreModel):
    path: str
    # Aliased under a short stable path because SSH control sockets embedded in
    # the workspace have a hard length limit.
    alias: str


class PresetSessionFinalize(CoreModel):
    """What a later detached reconcile needs to finalize the session."""

    project: str
    keep_service: bool


class PresetSessionRun(CoreModel):
    """One agent run over the session, recorded whole when the run begins."""

    workspace: PresetSessionWorkspace
    finalize: PresetSessionFinalize
    # A resume launches the same agent CLI the session started with.
    agent_provider: PresetAgentProvider
    # The model pinned by the user; None leaves the choice to the agent CLI.
    agent_model: Optional[str]
    # The agent process; None between attempts and after a detach outlives them.
    session_process: Optional[PresetSessionProcess]
    # The agent CLI's own session, which its resume continues; None until the
    # agent's stream reveals it.
    session_id: Optional[str]


class PresetSessionState(CoreModel):
    """`session.json`. The record fields never change after creation; `status`,
    `owner`, and `run` advance only through the `PresetSession` transitions."""

    id: str
    # Released when a newer preset claims the name — the one record mutation.
    name: Optional[str]
    model: str
    # None when the configuration left the trial count to the agent.
    trials_num: Optional[int]
    previous: list[str]
    created_at: datetime
    status: PresetSessionStatus
    # None is a detached session.
    owner: Optional[PresetSessionProcess]
    # None is a session that never began a run.
    run: Optional[PresetSessionRun]


class PresetAgentInfo(CoreModel):
    """`agent.json`: how the agent CLI was launched. A debug record."""

    provider: PresetAgentProvider
    executable: str
    version: Optional[str]
    auth_status: str
    # None is the agent CLI's default.
    effort: Optional[str]
    # Reported by the agent CLI once it starts; None until then.
    model: Optional[str]


class ClaudeStreamEvent(CoreModel):
    """One line of the claude CLI's `--output-format stream-json`. Not our format:
    unknown fields are dropped and omitted fields default."""

    # "system", "assistant", "user", "result", and whatever a newer claude CLI
    # adds — which is why this is not a Literal.
    type: str
    # Identifies the claude conversation, so an interrupted creation can be
    # resumed with `claude --resume`. Not every line carries it.
    session_id: Optional[str] = None
    # The model claude runs with, e.g. "claude-opus-5[1m]". Set on the init line only.
    model: Optional[str] = None


class ClaudeResultEvent(ClaudeStreamEvent):
    """The final line: the agent's structured output, or its error."""

    type: Literal["result"]
    is_error: bool = False
    # An error's message, or the report itself when the agent printed it instead
    # of submitting it through `StructuredOutput`; None when there was no text.
    result: Optional[Any] = None
    # The agent's final report, raw until `verify` parses it — that parse redacts
    # known secret values as it validates, so nothing downstream sees them.
    # None when the agent never submitted one.
    structured_output: Optional[Dict[str, Any]] = None


# Left to right so a result line always reads as `ClaudeResultEvent`.
AnyClaudeStreamEvent = Annotated[
    Union[ClaudeResultEvent, ClaudeStreamEvent], Field(union_mode="left_to_right")
]


class CodexStreamItem(CoreModel):
    # "agent_message", "command_execution", "web_search", "reasoning", and others.
    type: str
    # The message text of an "agent_message"; the final one is the JSON report.
    text: Optional[str] = None


class CodexStreamError(CoreModel):
    message: str


class CodexStreamEvent(CoreModel):
    """One line of `codex exec --json`. Not our format: unknown fields are dropped
    and omitted fields default."""

    # "thread.started", "turn.started", "item.started", "item.completed",
    # "turn.completed", "turn.failed", "error", and whatever a newer codex adds.
    type: str
    # On "thread.started": the id `codex exec resume` takes.
    thread_id: Optional[str] = None
    item: Optional[CodexStreamItem] = None
    # On "turn.failed".
    error: Optional[CodexStreamError] = None
    # On "error": a stream or API failure outside a turn.
    message: Optional[str] = None
