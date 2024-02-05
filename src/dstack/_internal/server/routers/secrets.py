from typing import List

from fastapi import APIRouter

from dstack._internal.core.models.runs import Run
from dstack._internal.core.models.secrets import Secret
from dstack._internal.server.schemas.secrets import (
    AddSecretRequest,
    DeleteSecretsRequest,
    GetSecretsRequest,
    ListSecretsRequest,
)

router = APIRouter(
    prefix="/api/project/{project_name}/secrets",
    tags=["secrets"],
)


@router.post("/list")
async def list_secrets(project_name: str, body: ListSecretsRequest) -> List[Run]:
    pass


@router.post("/get")
async def get_secret(project_name: str, body: GetSecretsRequest) -> Secret:
    pass


@router.post("/add")
async def add_or_update_secret(project_name: str, body: AddSecretRequest) -> Secret:
    pass


@router.post("/delete")
async def delete_secrets(project_name: str, body: DeleteSecretsRequest):
    pass
