from typing import Annotated, Any, Literal, Optional, Union

from pydantic import (
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
    model_validator,
)
from typing_extensions import Self

from dstack._internal.core.models.common import (
    CoreModel,
    EntityReference,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import ProfileParams

DEFAULT_INPUT_TOKENS = 1024
DEFAULT_OUTPUT_TOKENS = 1024
DEFAULT_BASELINE = True
DEFAULT_DATASET = "random"


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


def _drop_model_from_required(schema: dict) -> None:
    # `model` is synthesized from the top-level `base`/`repo` shorthand by a
    # before-validator, which JSON Schema consumers never run.
    required = [field for field in schema.get("required", []) if field != "model"]
    if required:
        schema["required"] = required
    else:
        schema.pop("required", None)


class PresetConfiguration(
    ProfileParams,
):
    model_config = ConfigDict(json_schema_extra=_drop_model_from_required)

    type: Annotated[Literal["preset"], Field(description="The configuration type")] = "preset"
    # TODO: Generate a random name when omitted, like runs and fleets do
    name: Annotated[
        Optional[str],
        Field(description="The preset name"),
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
    min_context_length: Annotated[
        Optional[PositiveInt],
        Field(description="The minimum required context length. Required for creation"),
    ] = None
    max_ttft: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The maximum p50 time to first token, in milliseconds, that any benchmark"
                " may report. Required for creation"
            )
        ),
    ] = None
    trials: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The number of benchmarked trials during preset creation"
                " before the best one is promoted. Required for creation"
            )
        ),
    ] = None
    previous: Annotated[
        Optional[list[str]],
        Field(
            description=(
                "The IDs of previous presets whose creation results the agent"
                " analyzes and improves on"
            )
        ),
    ] = None
    concurrency: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The number of simultaneous requests used for benchmarks during preset"
                " creation. Required for creation"
            )
        ),
    ] = None
    input_tokens: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The number of input tokens per request used for benchmarks during"
                f" preset creation. Defaults to `{DEFAULT_INPUT_TOKENS}`"
            )
        ),
    ] = None
    output_tokens: Annotated[
        Optional[Annotated[int, Field(ge=2)]],
        Field(
            description=(
                "The number of output tokens per request used for benchmarks during"
                f" preset creation. Defaults to `{DEFAULT_OUTPUT_TOKENS}`"
            )
        ),
    ] = None
    shared_prefix_tokens: Annotated[
        Optional[Annotated[int, Field(ge=0)]],
        Field(
            description=(
                "How many of `input_tokens` are a prefix identical in every benchmark request,"
                " as a repeated system prompt or conversation history would be. Defaults to `0`,"
                " meaning every request is fully unique"
            )
        ),
    ] = None
    dataset: Annotated[
        Optional[str],
        Field(
            description=(
                "The benchmark dataset used during preset creation: `random` for synthetic"
                " prompts shaped by `input_tokens` and `output_tokens`, a benchmark tool's"
                " dataset name (e.g. `sharegpt`, `spec_bench`), or a Hugging Face dataset ID."
                " Defaults to `random`"
            )
        ),
    ] = None
    baseline: Annotated[
        Optional[bool],
        Field(
            description=(
                "Whether the first trial must be a baseline that serves the model with the"
                " serving framework's recommended defaults instead of an optimization attempt."
                " Defaults to `true`"
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
    def effective_input_tokens(self) -> int:
        return self.input_tokens if self.input_tokens is not None else DEFAULT_INPUT_TOKENS

    @property
    def effective_output_tokens(self) -> int:
        return self.output_tokens if self.output_tokens is not None else DEFAULT_OUTPUT_TOKENS

    @property
    def effective_baseline(self) -> bool:
        return self.baseline if self.baseline is not None else DEFAULT_BASELINE

    @property
    def effective_dataset(self) -> str:
        return self.dataset if self.dataset is not None else DEFAULT_DATASET

    @field_validator("dataset")
    @classmethod
    def validate_dataset_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        # Stripped because the agent reports the dataset it actually loaded, and
        # the two are compared for equality when the preset is verified.
        value = value.strip()
        if not value:
            raise ValueError("dataset must be a non-empty string")
        return value

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        if self.dataset in (None, DEFAULT_DATASET):
            return self
        set_fields = [
            name
            for name in ("input_tokens", "output_tokens", "shared_prefix_tokens")
            if getattr(self, name) is not None
        ]
        if set_fields:
            raise ValueError(
                f"{', '.join(set_fields)} can only be set with the `random` dataset;"
                " a custom dataset defines its own request shape"
            )
        return self

    @model_validator(mode="after")
    def validate_shared_prefix_tokens(self) -> Self:
        # The prefix is carved out of the request, so something has to be left
        # to differ between requests.
        if self.shared_prefix_tokens is None:
            return self
        input_tokens = self.input_tokens or DEFAULT_INPUT_TOKENS
        if self.shared_prefix_tokens >= input_tokens:
            raise ValueError(
                f"shared_prefix_tokens must be less than input_tokens ({input_tokens})"
            )
        return self

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
    min_context_length: PositiveInt
    max_ttft: PositiveInt
    trials_num: PositiveInt
    concurrency: PositiveInt
    baseline: bool
    fleets: Annotated[list[str], Field(min_length=1)]
    env: list[str]


class PresetRandomConstraints(PresetConstraints):
    """Constraints for the synthetic `random` dataset, which the request shape defines."""

    input_tokens: PositiveInt
    output_tokens: Annotated[int, Field(ge=2)]
    shared_prefix_tokens: Annotated[int, Field(ge=0)]


class PresetDatasetConstraints(PresetConstraints):
    """Constraints for a named dataset, which defines its own request shape."""

    dataset: str


def _validate_model(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Preset model {field} must be a non-empty string")
    return value
