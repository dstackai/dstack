from typing import Annotated, Optional

from pydantic import BaseModel, Field

from dstack._internal.core.configurations import AnyRunConfiguration
from dstack._internal.core.profiles import Profile
from dstack._internal.core.repo import AnyRepoData


class SubmitRunRequest(BaseModel):
    repo_id: str
    repo_code_hash: Optional[str]
    repo_data: Annotated[AnyRepoData, Field(discriminator="repo_type")]
    configuration_path: str
    configuration: Annotated[AnyRunConfiguration, Field(discriminator="type")]
    profile: Profile
    ssh_key_pub: str
    code_hash: Optional[str]
