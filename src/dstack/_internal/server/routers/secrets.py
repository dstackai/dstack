from typing import List, Tuple

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.secrets import Secret
from dstack._internal.server.db import get_session
from dstack._internal.server.models import ProjectModel, UserModel
from dstack._internal.server.schemas.secrets import (
    CreateOrUpdateSecretRequest,
    DeleteSecretsRequest,
    GetSecretRequest,
)
from dstack._internal.server.security.permissions import ProjectAdmin
from dstack._internal.server.services import secrets as secrets_services
from dstack._internal.server.utils.routers import CustomORJSONResponse

router = APIRouter(
    prefix="/api/project/{project_name}/secrets",
    tags=["secrets"],
)


@router.post("/list", response_model=List[Secret])
async def list_secrets(
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    return CustomORJSONResponse(
        await secrets_services.list_secrets(
            session=session,
            project=project,
        )
    )


@router.post("/get", response_model=Secret)
async def get_secret(
    body: GetSecretRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    secret = await secrets_services.get_secret(
        session=session,
        project=project,
        name=body.name,
    )
    if secret is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(secret)


@router.post("/create_or_update", response_model=Secret)
async def create_or_update_secret(
    body: CreateOrUpdateSecretRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    return CustomORJSONResponse(
        await secrets_services.create_or_update_secret(
            session=session,
            project=project,
            name=body.name,
            value=body.value,
        )
    )


@router.post("/delete")
async def delete_secrets(
    body: DeleteSecretsRequest,
    session: AsyncSession = Depends(get_session),
    user_project: Tuple[UserModel, ProjectModel] = Depends(ProjectAdmin()),
):
    _, project = user_project
    await secrets_services.delete_secrets(
        session=session,
        project=project,
        names=body.secrets_names,
    )
