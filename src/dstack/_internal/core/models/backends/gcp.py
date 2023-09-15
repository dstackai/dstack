from typing import List

from pydantic import BaseModel
from typing_extensions import Literal


class GCPConfigInfo(BaseModel):
    type: Literal["gcp"] = "gcp"
    regions: List[str]


class GCPServiceAccountCreds(BaseModel):
    type: Literal["service_account"] = "service_account"
    filename: str
    data: str


class GCPConfigInfoWithCreds(GCPConfigInfo):
    creds: GCPServiceAccountCreds
