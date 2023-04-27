import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.security.http import HTTPAuthorizationCredentials
from typing_extensions import Annotated

from dstack.backend.local import LocalBackend
from dstack.hub.models import FileObject
from dstack.hub.routers.cache import get_backend
from dstack.hub.routers.util import error_detail, get_project
from dstack.hub.security.permissions import ProjectMember


async def project_member_from_query(project_name: str, token: Annotated[str, Query()]):
    return await ProjectMember()(
        project_name, HTTPAuthorizationCredentials(scheme="query", credentials=token)
    )


router = APIRouter(
    prefix="/api/project", tags=["storage"], dependencies=[Depends(project_member_from_query)]
)


@router.put("/{project_name}/storage/upload", response_model=FileObject)
async def put_file(project_name: str, key: Annotated[str, Query()], file: UploadFile):
    project = await get_project(project_name=project_name)
    backend = get_backend(project, repo=None)
    if not isinstance(backend, LocalBackend):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                error_detail(
                    "Project backend is not local", code="not_local_backend", loc=["project_name"]
                )
            ],
        )
    root_path = Path(backend._storage.root_path)
    target_path = (root_path / key).resolve()
    try:  # validate if target_path is inside the root_path
        object_key = target_path.relative_to(root_path)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[error_detail("Object key is illegal", code="illegal_key", loc=["key"])],
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("wb") as f:
        await asyncio.get_running_loop().run_in_executor(None, shutil.copyfileobj, file.file, f)
    return FileObject(object_key=str(object_key))
