import json
from typing import List, Optional

import sqlalchemy.exc
from fastapi import UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    RepoDoesNotExistError,
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.repos import (
    AnyRepoInfo,
    RepoHead,
    RepoHeadWithCreds,
)
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.server.models import (
    CodeModel,
    DecryptedString,
    ProjectModel,
    RepoCredsModel,
    RepoModel,
    UserModel,
)
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.utils.common import run_async
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def list_repos(
    session: AsyncSession,
    project: ProjectModel,
) -> List[RepoHead]:
    res = await session.execute(select(RepoModel).where(RepoModel.project_id == project.id))
    repos = res.scalars().all()
    return [repo_model_to_repo_head(r) for r in repos]


async def get_repo(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    repo_id: str,
    include_creds: bool,
) -> Optional[RepoHeadWithCreds]:
    repo = await get_repo_model(
        session=session,
        project=project,
        repo_id=repo_id,
    )
    if repo is None:
        return None
    if not include_creds or repo.type != RepoType.REMOTE:
        return RepoHeadWithCreds.parse_obj(repo_model_to_repo_head(repo))
    repo_creds = await get_repo_creds(
        session=session,
        repo=repo,
        user=user,
    )
    return repo_model_to_repo_head_with_creds(repo, repo_creds)


async def init_repo(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
    repo_creds: Optional[RemoteRepoCreds],
) -> RepoModel:
    repo = await create_or_update_repo(
        session=session,
        project=project,
        repo_id=repo_id,
        repo_info=repo_info,
    )
    if repo.type == RepoType.REMOTE:
        if repo_creds is not None:
            await create_or_update_repo_creds(
                session=session,
                repo=repo,
                user=user,
                creds=repo_creds,
            )
        else:
            await delete_repo_creds(
                session=session,
                repo=repo,
                user=user,
            )
    return repo


async def create_or_update_repo(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
) -> RepoModel:
    try:
        return await create_repo(
            session=session,
            project=project,
            repo_id=repo_id,
            repo_info=repo_info,
        )
    except ResourceExistsError:
        return await update_repo(
            session=session,
            project=project,
            repo_id=repo_id,
            repo_info=repo_info,
        )


async def create_repo(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
) -> RepoModel:
    repo = RepoModel(
        project_id=project.id,
        name=repo_id,
        type=RepoType(repo_info.repo_type),
        info=repo_info.json(),
    )
    try:
        async with session.begin_nested():
            session.add(repo)
    except sqlalchemy.exc.IntegrityError:
        raise ResourceExistsError()
    await session.commit()
    return repo


async def update_repo(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
) -> RepoModel:
    await session.execute(
        update(RepoModel)
        .where(
            RepoModel.project_id == project.id,
            RepoModel.name == repo_id,
        )
        .values(
            info=repo_info.json(),
        )
    )
    await session.commit()
    repo = await get_repo_model(session=session, project=project, repo_id=repo_id)
    if repo is None:
        raise ResourceNotExistsError()
    return repo


async def delete_repos(
    session: AsyncSession,
    project: ProjectModel,
    repos_ids: List[str],
):
    await session.execute(
        delete(RepoModel).where(RepoModel.project_id == project.id, RepoModel.name.in_(repos_ids))
    )
    await session.commit()
    logger.info("Deleted repos %s in project %s", repos_ids, project.name)


async def get_repo_creds(
    session: AsyncSession,
    repo: RepoModel,
    user: UserModel,
) -> Optional[RepoCredsModel]:
    res = await session.execute(
        select(RepoCredsModel).where(
            RepoCredsModel.repo_id == repo.id,
            RepoCredsModel.user_id == user.id,
        )
    )
    return res.scalar()


async def create_or_update_repo_creds(
    session: AsyncSession,
    repo: RepoModel,
    user: UserModel,
    creds: RemoteRepoCreds,
) -> RepoCredsModel:
    try:
        return await create_repo_creds(
            session=session,
            repo=repo,
            user=user,
            creds=creds,
        )
    except ResourceExistsError:
        return await update_repo_creds(
            session=session,
            repo=repo,
            user=user,
            creds=creds,
        )


async def create_repo_creds(
    session: AsyncSession,
    repo: RepoModel,
    user: UserModel,
    creds: RemoteRepoCreds,
) -> RepoCredsModel:
    repo_creds = RepoCredsModel(
        repo_id=repo.id,
        user_id=user.id,
        creds=DecryptedString(plaintext=creds.json()),
    )
    try:
        async with session.begin_nested():
            session.add(repo_creds)
    except sqlalchemy.exc.IntegrityError:
        raise ResourceExistsError()
    await session.commit()
    return repo_creds


async def update_repo_creds(
    session: AsyncSession,
    repo: RepoModel,
    user: UserModel,
    creds: RemoteRepoCreds,
) -> RepoCredsModel:
    await session.execute(
        update(RepoCredsModel)
        .where(
            RepoCredsModel.repo_id == repo.id,
            RepoCredsModel.user_id == user.id,
        )
        .values(
            creds=DecryptedString(plaintext=creds.json()),
        )
    )
    await session.commit()
    repo_creds = await get_repo_creds(session=session, repo=repo, user=user)
    if repo_creds is None:
        raise ResourceNotExistsError()
    return repo_creds


async def delete_repo_creds(
    session: AsyncSession,
    repo: RepoModel,
    user: UserModel,
):
    await session.execute(
        delete(RepoCredsModel).where(
            RepoCredsModel.repo_id == repo.id,
            RepoCredsModel.user_id == user.id,
        )
    )
    await session.commit()
    logger.info("Deleted repo creds for repo %s user %s", repo.name, user.name)


async def upload_code(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    file: UploadFile,
):
    repo = await get_repo_model(session=session, project=project, repo_id=repo_id)
    if repo is None:
        raise RepoDoesNotExistError.with_id(repo_id)
    if file.filename is None:
        raise ServerClientError("filename not specified")
    code_hash = file.filename
    code = await get_code_model(
        session=session,
        repo=repo,
        code_hash=code_hash,
    )
    if code is not None:
        return
    blob = await file.read()
    storage = get_default_storage()
    if storage is None:
        code = CodeModel(
            repo_id=repo.id,
            blob_hash=code_hash,
            blob=blob,
        )
    else:
        code = CodeModel(
            repo_id=repo.id,
            blob_hash=code_hash,
            blob=None,
        )
        await run_async(storage.upload_code, project.name, repo.name, code.blob_hash, blob)
    session.add(code)
    await session.commit()


async def get_repo_model(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
) -> Optional[RepoModel]:
    res = await session.execute(
        select(RepoModel).where(
            RepoModel.project_id == project.id,
            RepoModel.name == repo_id,
        )
    )
    return res.scalar()


async def get_code_model(
    session: AsyncSession,
    repo: RepoModel,
    code_hash: str,
) -> Optional[CodeModel]:
    res = await session.execute(
        select(CodeModel).where(
            CodeModel.repo_id == repo.id,
            CodeModel.blob_hash == code_hash,
        )
    )
    return res.scalar()


def repo_model_to_repo_head(repo_model: RepoModel) -> RepoHead:
    return RepoHead.__response__.parse_obj(
        {
            "repo_id": repo_model.name,
            "repo_info": json.loads(repo_model.info),
        }
    )


def repo_model_to_repo_head_with_creds(
    repo_model: RepoModel, repo_creds_model: Optional[RepoCredsModel]
) -> RepoHeadWithCreds:
    repo_creds_raw: Optional[str]
    if repo_creds_model is None:
        repo_creds_raw = repo_model.creds
    else:
        repo_creds_raw = repo_creds_model.creds.plaintext
    return RepoHeadWithCreds.__response__.parse_obj(
        {
            "repo_id": repo_model.name,
            "repo_info": json.loads(repo_model.info),
            "repo_creds": json.loads(repo_creds_raw) if repo_creds_raw else None,
        }
    )
