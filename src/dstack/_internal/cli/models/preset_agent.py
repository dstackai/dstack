import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, Literal, Optional, Union

import yaml
from pydantic import (
    Field,
    PositiveInt,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)

from dstack._internal.cli.models.presets import PresetBenchmark
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.configurations import ServiceConfiguration


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
    context_length: PositiveInt
    benchmark: PresetBenchmark


class PresetAgentFailure(CoreModel):
    """Why the agent created no preset."""

    success: Literal[False]
    failure_summary: str


AnyPresetAgentResult = Union[PresetAgentSuccess, PresetAgentFailure]


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
    # Only known when this CLI launched the agent; a follower leaves it as is.
    claude_model: Optional[str]
    # None between claude process attempts and after a detach outlives them.
    agent: Optional[PresetSessionProcess]
    # None until the agent's stream reveals it.
    claude_session_id: Optional[str]


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
    debug: bool
    status: PresetSessionStatus
    # None is a detached session.
    owner: Optional[PresetSessionProcess]
    # None is a session that never began a run.
    run: Optional[PresetSessionRun]


class ClaudeStreamEvent(CoreModel):
    """One line of the claude CLI's `--output-format stream-json`. Not our format:
    unknown fields are dropped and omitted fields default."""

    # "system", "assistant", "user", "result", and whatever a newer claude CLI
    # adds — which is why this is not a Literal.
    type: str
    # Identifies the claude conversation, so an interrupted creation can be
    # resumed with `claude --resume`. Not every line carries it.
    session_id: Optional[str] = None


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
