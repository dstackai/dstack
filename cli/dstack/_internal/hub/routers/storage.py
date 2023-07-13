from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from fastapi.security.http import HTTPAuthorizationCredentials
from typing_extensions import Annotated

from dstack._internal.backend.base import Backend
from dstack._internal.backend.local import LocalBackend
from dstack._internal.hub.models import FileObject
from dstack._internal.hub.routers.util import error_detail, get_backend, get_project
from dstack._internal.hub.security.permissions import ProjectMember


async def project_member_from_query(project_name: str, token: Annotated[str, Query()]):
    return await ProjectMember()(
        project_name, HTTPAuthorizationCredentials(scheme="query", credentials=token)
    )


router = APIRouter(
    prefix="/api/project", tags=["storage"], dependencies=[Depends(project_member_from_query)]
)


@router.put("/{project_name}/storage/upload", response_model=FileObject)
async def put_file(project_name: str, key: Annotated[str, Query()], request: Request):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    _check_backend_local(backend)
    root_path = Path(backend._storage.root_path).resolve()
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
        async for chunk in request.stream():
            f.write(chunk)
    return FileObject(object_key=str(object_key))


@router.get("/{project_name}/storage/download", response_model=FileObject)
async def download_file(project_name: str, key: Annotated[str, Query()], request: Request):
    project = await get_project(project_name=project_name)
    backend = await get_backend(project)
    _check_backend_local(backend)
    root_path = Path(backend._storage.root_path).resolve()
    target_path = (root_path / key).resolve()
    try:
        target_path.relative_to(root_path)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[error_detail("Object key is illegal", code="illegal_key", loc=["key"])],
        )
    return FileResponse(path=target_path)


def _check_backend_local(backend: Backend):
    if not isinstance(backend, LocalBackend):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=[
                error_detail(
                    "Project backend is not local", code="not_local_backend", loc=["project_name"]
                )
            ],
        )
