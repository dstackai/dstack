from typing import List

from dstack._internal.core.models.common import CoreModel


class GetSecretRequest(CoreModel):
    name: str


class CreateOrUpdateSecretRequest(CoreModel):
    name: str
    value: str


class DeleteSecretsRequest(CoreModel):
    secrets_names: List[str]
