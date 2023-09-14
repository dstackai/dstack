from typing import Annotated, Optional

from pydantic import BaseModel, Field

from dstack._internal.core.models.configurations import AnyRunConfiguration
from dstack._internal.core.models.profiles import Profile
from dstack._internal.core.models.repos import AnyRunRepoData


class SubmitRunRequest(BaseModel):
    repo_id: str
    repo_data: Annotated[AnyRunRepoData, Field(discriminator="repo_type")]
    repo_code_hash: Optional[str]
    configuration_path: str
    configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]
    profile: Profile
    ssh_key_pub: str
