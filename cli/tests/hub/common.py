import json
from typing import Dict, Optional

from dstack.hub.db.models import Project, User
from dstack.hub.repository.projects import ProjectManager
from dstack.hub.repository.users import UserManager


async def create_user(
    name: str = "test_user",
    global_role: str = "admin",
    token: str = "1234",
) -> User:
    user = User(
        name=name,
        global_role=global_role,
        token=token,
    )
    await UserManager.save(user)
    return user


async def create_project(
    name: str = "test_project",
    backend: str = "aws",
    config: Optional[Dict] = None,
    auth: Optional[Dict] = None,
) -> Project:
    if config is None:
        config = {
            "region_name": "eu-west-1",
            "s3_bucket_name": "dstack-test-eu-west-1",
            "ec2_subnet_id": None,
        }
    if auth is None:
        auth = {
            "access_key": "test_access_key",
            "secret_key": "test_secret_key",
        }
    project = Project(
        name=name,
        backend=backend,
        config=json.dumps(config),
        auth=json.dumps(auth),
    )
    await ProjectManager.create(project)
    return project
