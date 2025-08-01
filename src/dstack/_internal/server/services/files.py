import uuid
from typing import Optional

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.files import FileArchive
from dstack._internal.server.models import FileArchiveModel, UserModel
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def get_archive_model(
    session: AsyncSession,
    id: uuid.UUID,
    user: Optional[UserModel] = None,
) -> Optional[FileArchiveModel]:
    stmt = select(FileArchiveModel).where(FileArchiveModel.id == id)
    if user is not None:
        stmt = stmt.where(FileArchiveModel.user_id == user.id)
    res = await session.execute(stmt)
    return res.scalar()


async def get_archive_model_by_hash(
    session: AsyncSession,
    user: UserModel,
    hash: str,
) -> Optional[FileArchiveModel]:
    res = await session.execute(
        select(FileArchiveModel).where(
            FileArchiveModel.user_id == user.id,
            FileArchiveModel.blob_hash == hash,
        )
    )
    return res.scalar()


async def get_archive_by_hash(
    session: AsyncSession,
    user: UserModel,
    hash: str,
) -> Optional[FileArchive]:
    archive_model = await get_archive_model_by_hash(
        session=session,
        user=user,
        hash=hash,
    )
    if archive_model is None:
        return None
    return archive_model_to_archive(archive_model)


async def upload_archive(
    session: AsyncSession,
    user: UserModel,
    file: UploadFile,
) -> FileArchive:
    if file.filename is None:
        raise ServerClientError("filename not specified")
    archive_hash = file.filename
    archive_model = await get_archive_model_by_hash(
        session=session,
        user=user,
        hash=archive_hash,
    )
    if archive_model is not None:
        logger.debug("File archive (user_id=%s, hash=%s) already uploaded", user.id, archive_hash)
        return archive_model_to_archive(archive_model)
    blob = await file.read()
    storage = get_default_storage()
    if storage is not None:
        await run_async(storage.upload_archive, str(user.id), archive_hash, blob)
    archive_model = FileArchiveModel(
        user_id=user.id,
        blob_hash=archive_hash,
        blob=blob if storage is None else None,
    )
    session.add(archive_model)
    await session.commit()
    logger.debug("File archive (user_id=%s, hash=%s) has been uploaded", user.id, archive_hash)
    return archive_model_to_archive(archive_model)


def archive_model_to_archive(archive_model: FileArchiveModel) -> FileArchive:
    return FileArchive(id=archive_model.id, hash=archive_model.blob_hash)
