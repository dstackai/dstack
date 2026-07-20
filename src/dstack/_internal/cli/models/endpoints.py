from typing import Annotated, Any, Literal, Optional, Union

from pydantic import Field, PositiveInt, validator

from dstack._internal.core.models.common import (
    CoreModel,
    EntityReference,
    generate_dual_core_model,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import ProfileParams, ProfileParamsConfig
from dstack._internal.utils.json_schema import add_extra_schema_types

DEFAULT_MAX_TRIALS = 3
DEFAULT_CONCURRENCY = 8


class EndpointModelRepo(CoreModel):
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

    @validator("repo")
    def validate_repo(cls, value: str) -> str:
        return _validate_model(value, field="repo")

    @validator("name")
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _validate_model(value, field="name")


class EndpointModelBase(CoreModel):
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

    @validator("base")
    def validate_base(cls, value: str) -> str:
        return _validate_model(value, field="base")


EndpointModelSpec = Union[EndpointModelRepo, EndpointModelBase]


class EndpointConfigurationConfig(ProfileParamsConfig):
    @staticmethod
    def schema_extra(schema: dict[str, Any]):
        ProfileParamsConfig.schema_extra(schema)
        add_extra_schema_types(
            schema["properties"]["model"],
            extra_types=[{"type": "string"}],
        )


class EndpointConfiguration(
    ProfileParams,
    generate_dual_core_model(EndpointConfigurationConfig),
):
    type: Annotated[Literal["endpoint"], Field(description="The configuration type")] = "endpoint"
    name: Annotated[
        Optional[str],
        Field(description="The endpoint name. Required unless passed with `--name`"),
    ] = None
    model: Annotated[
        EndpointModelSpec,
        Field(
            description=(
                "The model to serve. Use a string or `repo` for an exact repo/path, "
                "or `base` to allow compatible model variants."
            )
        ),
    ]
    context_length: Annotated[
        Optional[PositiveInt], Field(description="The minimum required context length")
    ] = None
    preset: Annotated[
        Optional[str], Field(description="The preset ID to use when applying the endpoint")
    ] = None
    max_trials: Annotated[
        Optional[PositiveInt],
        Field(
            description=(
                "The maximum number of benchmarked trials during preset creation"
                f" before the best one is promoted. Defaults to `{DEFAULT_MAX_TRIALS}`"
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
            description=(
                "The name of the gateway. Specify boolean `false` to run without a gateway."
                " Specify boolean `true` to run with the default gateway."
                " Omit to run with the default gateway if there is one, or without a gateway otherwise"
            )
        ),
    ] = None
    env: Annotated[Env, Field(description="The mapping or the list of environment variables")] = (
        Env()
    )

    @property
    def effective_max_trials(self) -> int:
        return self.max_trials if self.max_trials is not None else DEFAULT_MAX_TRIALS

    @property
    def effective_concurrency(self) -> int:
        return self.concurrency if self.concurrency is not None else DEFAULT_CONCURRENCY

    @validator("model", pre=True)
    def parse_model(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"repo": _validate_model(value, field="model")}
        return value

    @validator("preset")
    def validate_preset(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("Endpoint preset must be a non-empty string")
        return value


class EndpointPresetConstraints(CoreModel):
    """The effective constraints for endpoint preset creation, saved as `constraints.json`
    in the agent workspace. Field semantics are documented in the agent system prompt."""

    run_name_prefix: str
    model: EndpointModelSpec
    context_length: Optional[PositiveInt] = None
    max_trials: PositiveInt
    concurrency: PositiveInt
    fleets: list[str] = Field(min_items=1)
    env: list[str] = []


def _validate_model(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Endpoint model {field} must be a non-empty string")
    return value
