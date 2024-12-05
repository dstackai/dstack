from typing import Annotated

from pydantic import Field

from dstack._internal.core.models.common import CoreModel


class RepoRequest(CoreModel):
    repo_id: Annotated[str, Field(description="A unique identifier of the repo")]
