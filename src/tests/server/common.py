import json
import uuid
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.repos.base import RepoType
from dstack._internal.core.models.users import GlobalRole
from dstack._internal.server.models import BackendModel, ProjectModel, RepoModel, UserModel


def get_auth_headers(token: str) -> Dict:
    return {"Authorization": f"Bearer {token}"}


async def create_user(
    session: AsyncSession,
    name: str = "test_user",
    global_role: GlobalRole = GlobalRole.ADMIN,
    token: Optional[str] = None,
) -> UserModel:
    if token is None:
        token = str(uuid.uuid4())
    user = UserModel(
        name=name,
        global_role=global_role,
        token=token,
    )
    session.add(user)
    await session.commit()
    return user


async def create_project(
    session: AsyncSession,
    name: str = "test_project",
    ssh_private_key: str = "",
    ssh_public_key: str = "",
) -> ProjectModel:
    project = ProjectModel(
        name=name,
        ssh_private_key=ssh_private_key,
        ssh_public_key=ssh_public_key,
    )
    session.add(project)
    await session.commit()
    return project


async def create_backend(
    session: AsyncSession,
    project_id: uuid.UUID,
    backend_type: BackendType = BackendType.AWS,
    config: Optional[Dict] = None,
    auth: Optional[Dict] = None,
) -> BackendModel:
    if config is None:
        config = {
            "regions": ["eu-west-1"],
        }
    if auth is None:
        auth = {
            "type": "access_key",
            "access_key": "test_access_key",
            "secret_key": "test_secret_key",
        }
    backend = BackendModel(
        project_id=project_id,
        type=backend_type,
        config=json.dumps(config),
        auth=json.dumps(auth),
    )
    session.add(backend)
    await session.commit()
    return backend


async def create_repo(
    session: AsyncSession,
    project_id: uuid.UUID,
    repo_id: str = "test_repo",
    repo_type: RepoType = RepoType.REMOTE,
    info: Optional[Dict] = None,
    creds: Optional[Dict] = None,
):
    if info is None:
        info = {
            "repo_type": "remote",
            "repo_host_name": "github.com",
            "repo_port": None,
            "repo_user_name": "dstackai",
            "repo_name": "dstack",
        }
    if creds is None:
        creds = {
            "protocol": "https",
            "private_key": None,
            "oauth_token": "test_token",
        }
    repo = RepoModel(
        project_id=project_id,
        name=repo_id,
        type=repo_type,
        info=json.dumps(info),
        creds=json.dumps(creds),
    )
    session.add(repo)
    await session.commit()
    return repo
