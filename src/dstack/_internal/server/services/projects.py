from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.models.projects import Member, Project
from dstack._internal.core.models.users import ProjectRole
from dstack._internal.server.models import MemberModel, ProjectModel, UserModel
from dstack._internal.server.services import users
from dstack._internal.server.services.backends import get_configurator
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes


async def list_user_projects(
    session: AsyncSession,
    user: UserModel,
) -> List[Project]:
    res = await session.execute(
        select(MemberModel)
        .options(joinedload(MemberModel.project))
        .where(MemberModel.user_id == user.id)
    )
    members = res.scalars().all()
    project_models = [m.project for m in members]
    return [project_model_to_project(p) for p in project_models]


async def create_project(
    session: AsyncSession, user: UserModel, project_name: str
) -> ProjectModel:
    private_bytes, public_bytes = await run_async(
        generate_rsa_key_pair_bytes, f"{project_name}@dstack"
    )
    project = ProjectModel(
        name=project_name,
        ssh_private_key=private_bytes.decode(),
        ssh_public_key=public_bytes.decode(),
    )
    session.add(project)
    await session.commit()
    await add_project_member(
        session=session,
        project=project,
        user=user,
        project_role=ProjectRole.ADMIN,
    )
    return project


async def add_project_member(
    session: AsyncSession, project: ProjectModel, user: UserModel, project_role: ProjectRole
) -> MemberModel:
    member = MemberModel(
        user_id=user.id,
        project_id=project.id,
        project_role=project_role,
    )
    session.add(member)
    await session.commit()
    return member


async def get_project_model_by_name(
    session: AsyncSession,
    project_name: str,
) -> Optional[ProjectModel]:
    res = await session.execute(select(ProjectModel).where(ProjectModel.name == project_name))
    return res.scalar()


def project_model_to_project(project_model: ProjectModel) -> Project:
    members = []
    for m in project_model.members:
        members.append(
            Member(
                user=users.user_model_to_user(m.user),
                project_role=m.project_role,
            )
        )
    backends = []
    for b in project_model.backends:
        configurator = get_configurator(b.type)
        backends.append(configurator.get_backend_config())
    return Project(
        project_id=project_model.id,
        project_name=project_model.name,
        backends=backends,
        members=members,
    )
