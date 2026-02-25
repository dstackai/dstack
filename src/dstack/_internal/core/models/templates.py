from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class BaseUITemplateParameter(CoreModel):
    """Base for all UI template parameters."""

    pass


class NameUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["name"], Field(description="The parameter type")]


class IDEUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["ide"], Field(description="The parameter type")]


class ResourcesUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["resources"], Field(description="The parameter type")]


class PythonOrDockerUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["python_or_docker"], Field(description="The parameter type")]


class RepoUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["repo"], Field(description="The parameter type")]


class WorkingDirUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["working_dir"], Field(description="The parameter type")]


class EnvUITemplateParameter(BaseUITemplateParameter):
    type: Annotated[Literal["env"], Field(description="The parameter type")]
    title: Annotated[Optional[str], Field(description="The display title")] = None
    name: Annotated[Optional[str], Field(description="The environment variable name")] = None
    value: Annotated[Optional[str], Field(description="The default value")] = None


AnyUITemplateParameter = Annotated[
    Union[
        NameUITemplateParameter,
        IDEUITemplateParameter,
        ResourcesUITemplateParameter,
        PythonOrDockerUITemplateParameter,
        RepoUITemplateParameter,
        WorkingDirUITemplateParameter,
        EnvUITemplateParameter,
    ],
    Field(discriminator="type"),
]


class UITemplate(CoreModel):
    type: Annotated[Literal["template"], Field(description="The template type")]
    name: Annotated[str, Field(description="The unique template identifier")]
    title: Annotated[str, Field(description="The human-readable template name")]
    description: Annotated[Optional[str], Field(description="The template description")] = None
    parameters: Annotated[
        List[AnyUITemplateParameter],
        Field(description="The template parameters"),
    ] = []
    configuration: Annotated[
        Dict[str, Any],
        Field(description="The dstack run configuration"),
    ]
