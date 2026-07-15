from typing import Annotated, Any, Literal, Optional, Union

from pydantic import Field, PositiveInt, validator

from dstack._internal.core.models.common import CoreModel, EntityReference
from dstack._internal.core.models.envs import Env
from dstack._internal.core.models.profiles import ProfileParams


class EndpointModelRepo(CoreModel):
    repo: str
    """Exact repo/path to deploy."""
    name: Optional[str] = None
    """Client-facing model name. Defaults to `repo`."""

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
    base: str
    """Base model for which the agent may select a compatible variant."""

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


class EndpointConfiguration(ProfileParams):
    type: Literal["endpoint"] = "endpoint"
    name: Optional[str] = None
    model: Annotated[
        EndpointModelSpec,
        Field(
            description=(
                "The model to serve. Use a string or `repo` for an exact repo/path, "
                "or `base` to allow compatible model variants."
            )
        ),
    ]
    context_length: Optional[PositiveInt] = None
    """Minimum context length required from the endpoint."""
    preset: Optional[str] = None
    """Preset ID to use when applying an endpoint preset."""
    gateway: Optional[Union[bool, EntityReference, str]] = None
    env: Env = Env()

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


def _validate_model(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Endpoint model {field} must be a non-empty string")
    return value
