from typing import Annotated

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError, ServerClientError
from dstack._internal.core.models.files import FileArchive
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.files import GetFileArchiveByHashRequest
from dstack._internal.server.security.permissions import Authenticated
from dstack._internal.server.services import files
from dstack._internal.server.settings import SERVER_CODE_UPLOAD_LIMIT
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
    get_request_size,
)
from dstack._internal.utils.common import sizeof_fmt

router = APIRouter(
    prefix="/api/files",
    tags=["files"],
    responses=get_base_api_additional_responses(),
)


@router.post("/get_archive_by_hash", response_model=FileArchive)
async def get_archive_by_hash(
    body: GetFileArchiveByHashRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserModel, Depends(Authenticated())],
):
    archive = await files.get_archive_by_hash(
        session=session,
        user=user,
        hash=body.hash,
    )
    if archive is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(archive)


@router.post("/upload_archive", response_model=FileArchive)
async def upload_archive(
    request: Request,
    file: UploadFile,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[UserModel, Depends(Authenticated())],
):
    request_size = get_request_size(request)
    if SERVER_CODE_UPLOAD_LIMIT > 0 and request_size > SERVER_CODE_UPLOAD_LIMIT:
        diff_size_fmt = sizeof_fmt(request_size)
        limit_fmt = sizeof_fmt(SERVER_CODE_UPLOAD_LIMIT)
        if diff_size_fmt == limit_fmt:
            diff_size_fmt = f"{request_size}B"
            limit_fmt = f"{SERVER_CODE_UPLOAD_LIMIT}B"
        raise ServerClientError(
            f"Archive size is {diff_size_fmt}, which exceeds the limit of {limit_fmt}."
            " Use .gitignore/.dstackignore to exclude large files."
            " This limit can be modified by setting the DSTACK_SERVER_CODE_UPLOAD_LIMIT environment variable."
        )
    archive = await files.upload_archive(
        session=session,
        user=user,
        file=file,
    )
    return CustomORJSONResponse(archive)
