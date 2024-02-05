import json
from typing import List, Optional

import sqlalchemy.exc
from fastapi import UploadFile
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import RepoDoesNotExistError, ServerClientError
from dstack._internal.core.models.repos import (
    AnyRepoHead,
    AnyRepoInfo,
    RepoHead,
    RepoHeadWithCreds,
)
from dstack._internal.core.models.repos.remote import RemoteRepoCreds
from dstack._internal.server.models import CodeModel, ProjectModel, RepoModel
from dstack._internal.server.services.storage import get_default_storage
from dstack._internal.server.utils.common import run_async


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
    return repo_model_to_repo_head(repo, include_creds=include_creds)


async def init_repo(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
    repo_creds: Optional[RemoteRepoCreds],
) -> RepoModel:
    try:
        return await create_repo(
            session=session,
            project=project,
            repo_id=repo_id,
            repo_info=repo_info,
            repo_creds=repo_creds,
        )
    except sqlalchemy.exc.IntegrityError:
        await session.rollback()
        await session.refresh(project)
        return await update_repo(
            session=session,
            project=project,
            repo_id=repo_id,
            repo_info=repo_info,
            repo_creds=repo_creds,
        )


async def create_repo(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
    repo_creds: Optional[RemoteRepoCreds],
) -> RepoModel:
    repo = RepoModel(
        project_id=project.id,
        name=repo_id,
        type=repo_info.repo_type,
        info=repo_info.json(),
        creds=repo_creds.json() if repo_creds else None,
    )
    session.add(repo)
    await session.commit()
    return repo


async def update_repo(
    session: AsyncSession,
    project: ProjectModel,
    repo_id: str,
    repo_info: AnyRepoInfo,
    repo_creds: Optional[RemoteRepoCreds],
) -> RepoModel:
    repo = RepoModel(
        project_id=project.id,
        name=repo_id,
        type=repo_info.repo_type,
        info=repo_info.json(),
        creds=repo_creds.json() if repo_creds else None,
    )
    await session.execute(
        update(RepoModel)
        .where(
            RepoModel.project_id == project.id,
            RepoModel.name == repo_id,
        )
        .values(
            info=repo.info,
            creds=repo.creds,
        )
    )
    await session.commit()
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


def repo_model_to_repo_head(
    repo_model: RepoModel,
    include_creds: bool = False,
) -> AnyRepoHead:
    if include_creds:
        return RepoHeadWithCreds.parse_obj(
            {
                "repo_id": repo_model.name,
                "repo_info": json.loads(repo_model.info),
                "repo_creds": json.loads(repo_model.creds) if repo_model.creds else None,
            }
        )
    return RepoHead.parse_obj(
        {
            "repo_id": repo_model.name,
            "repo_info": json.loads(repo_model.info),
        }
    )
