from typing import Annotated, Any, Literal, Optional, Union

from pydantic import (
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)

from dstack._internal.core.models.common import (
    CoreModel,
    EntityReference,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import ProfileParams

DEFAULT_CONCURRENCY = 8


class PresetModelRepo(CoreModel):
    repo: Annotated[str, Field(description="The exact model repo or path to deploy")]
    name: Annotated[
        Optional[str], Field(description="The client-facing model name. Defaults to `repo`")
    ] = None

    @property
    def api_model_name(self) -> str:
        return self.name or self.repo

    @property
    def exact_repo(self) -> str:
        return self.repo

    @property
    def allows_variant_selection(self) -> bool:
        return False

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        return _validate_model(value, field="repo")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _validate_model(value, field="name")


class PresetModelBase(CoreModel):
    base: Annotated[
        str,
        Field(description="The base model for which the agent may select a compatible variant"),
    ]

    @property
    def api_model_name(self) -> str:
        return self.base

    @property
    def exact_repo(self) -> None:
        return None

    @property
    def allows_variant_selection(self) -> bool:
        return True

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str) -> str:
        return _validate_model(value, field="base")


PresetModelSpec = Union[PresetModelRepo, PresetModelBase]

MAX_PROMPT_LENGTH = 10_000


class PresetPromptFile(CoreModel):
    path: Annotated[
        str,
        Field(description="The path to a prompt file, relative to the configuration file"),
    ]

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Prompt path must be a non-empty string")
        return value


class PresetConfiguration(
    ProfileParams,
):
    type: Annotated[Literal["preset"], Field(description="The configuration type")] = "preset"
    name: Annotated[
        Optional[str],
        Field(description="The service name. Required unless passed with `--name`"),
    ] = None
    model: Annotated[
        PresetModelSpec,
        Field(
            description=(
                "The model to serve. Use a string or `repo` for an exact repo/path, "
                "or `base` to allow compatible model variants. "
                "Prefer the top-level `base`/`repo` shorthand unless a custom "
                "client-facing model name is needed"
            )
        ),
    ]
    base: Annotated[
        Optional[str],
        Field(
            description=(
                "The base model repo; compatible variants are allowed. Shorthand for `model.base`"
            )
        ),
    ] = None
    repo: Annotated[
        Optional[str],
        Field(description="The exact model repo/path to serve. Shorthand for `model.repo`"),
    ] = None
    prompt: Annotated[
        Optional[Union[str, PresetPromptFile]],
        Field(
            description=(
                "Additional instructions for the preset creation agent, inline or as a file `path`"
            )
        ),
    ] = None
    context_length: Annotated[
        Optional[PositiveInt], Field(description="The minimum required context length")
    ] = None
    max_trials: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The maximum number of benchmarked trials during preset creation"
                " before the best one is promoted"
            )
        ),
    ] = None
    concurrency: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The number of simultaneous requests used for benchmarks during"
                f" preset creation. Defaults to `{DEFAULT_CONCURRENCY}`"
            )
        ),
    ] = None
    gateway: Annotated[
        Optional[Union[bool, EntityReference, str]],
        Field(
            union_mode="left_to_right",  # preserving pydantic v1 parsing behavior
            description=(
                "The name of the gateway. Specify boolean `false` to run without a gateway."
                " Specify boolean `true` to run with the default gateway."
                " Omit to run with the default gateway if there is one, or without a gateway otherwise"
            ),
        ),
    ] = None
    env: Annotated[Env, Field(description="The mapping or the list of environment variables")] = (
        Env()
    )

    @property
    def effective_concurrency(self) -> int:
        return self.concurrency if self.concurrency is not None else DEFAULT_CONCURRENCY

    @model_validator(mode="before")
    @classmethod
    def apply_model_shorthand(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        base, repo = values.get("base"), values.get("repo")
        if base and repo:
            raise ValueError("`base` and `repo` are mutually exclusive")
        if base or repo:
            if values.get("model") is not None:
                raise ValueError("`model` cannot be combined with the `base`/`repo` shorthand")
            values = dict(values)
            values.pop("base", None)
            values.pop("repo", None)
            values["model"] = {"base": base} if base else {"repo": repo}
        return values

    @field_validator("model", mode="before", json_schema_input_type=Union[PresetModelSpec, str])
    @classmethod
    def parse_model(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"repo": _validate_model(value, field="model")}
        return value

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: Any) -> Any:
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("Prompt must be a non-empty string")
            if len(value) > MAX_PROMPT_LENGTH:
                raise ValueError(f"Prompt must be at most {MAX_PROMPT_LENGTH} characters")
        return value


class PresetConstraints(CoreModel):
    """The effective constraints for preset creation, saved as `constraints.json`
    in the agent workspace. Field semantics are documented in the agent system prompt."""

    run_name_prefix: str
    model: PresetModelSpec
    context_length: Optional[PositiveInt] = None
    max_trials: PositiveInt
    concurrency: PositiveInt
    fleets: list[str] = Field(min_length=1)
    env: list[str] = []


def _validate_model(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Preset model {field} must be a non-empty string")
    return value
