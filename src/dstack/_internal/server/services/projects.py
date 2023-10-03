import uuid
from typing import List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from dstack._internal.core.errors import ForbiddenError
from dstack._internal.core.models.backends import BackendInfo
from dstack._internal.core.models.projects import Member, Project
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import MemberModel, ProjectModel, UserModel
from dstack._internal.server.schemas.projects import MemberSetting
from dstack._internal.server.services import users
from dstack._internal.server.services.backends import get_configurator
from dstack._internal.server.settings import DEFAULT_PROJECT_NAME
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes


async def get_or_create_default_project(
    session: AsyncSession, user: UserModel
) -> Tuple[Project, bool]:
    default_project = await get_project_by_name(
        session=session,
        project_name=DEFAULT_PROJECT_NAME,
    )
    if default_project is not None:
        return default_project, False
    default_project = await create_project(
        session=session, user=user, project_name=DEFAULT_PROJECT_NAME
    )
    return default_project, True


async def list_user_projects(
    session: AsyncSession,
    user: UserModel,
) -> List[Project]:
    projects = await list_user_project_models(session=session, user=user)
    return [project_model_to_project(p) for p in projects]


async def list_projects(session: AsyncSession) -> List[Project]:
    projects = await list_project_models(session=session)
    return [project_model_to_project(p) for p in projects]


async def get_project_by_name(
    session: AsyncSession,
    project_name: str,
) -> Optional[Project]:
    project_model = await get_project_model_by_name(session=session, project_name=project_name)
    if project_model is None:
        return None
    return project_model_to_project(project_model)


async def create_project(session: AsyncSession, user: UserModel, project_name: str) -> Project:
    project = await create_project_model(session=session, project_name=project_name)
    await add_project_member(
        session=session,
        project=project,
        user=user,
        project_role=ProjectRole.ADMIN,
    )
    project = await get_project_model_by_name(session=session, project_name=project_name)
    return project_model_to_project(project)


async def delete_projects(
    session: AsyncSession,
    user: UserModel,
    projects_names: List[str],
):
    user_projects = await list_user_project_models(session=session, user=user)
    user_project_names = [p.name for p in user_projects]
    for project_name in projects_names:
        if project_name not in user_project_names:
            raise ForbiddenError()
    if user.global_role != GlobalRole.ADMIN:
        for project in user_projects:
            if not _is_project_admin(user=user, project=project):
                raise ForbiddenError()
    await session.execute(delete(ProjectModel).where(ProjectModel.name.in_(projects_names)))


async def add_project_member(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    project_role: ProjectRole,
    commit: bool = True,
) -> MemberModel:
    member = MemberModel(
        user_id=user.id,
        project_id=project.id,
        project_role=project_role,
    )
    session.add(member)
    if commit:
        await session.commit()
    return member


async def set_project_members(
    session: AsyncSession,
    project: ProjectModel,
    members: List[MemberSetting],
):
    usernames = [m.username for m in members]
    res = await session.execute(select(UserModel).where(UserModel.name.in_(usernames)))
    users = res.scalars().all()
    await clear_project_members(session=session, project=project, users=users)
    for user, member in zip(users, members):
        await add_project_member(
            session=session,
            project=project,
            user=user,
            project_role=member.project_role,
            commit=False,
        )
    await session.commit()


async def clear_project_members(
    session: AsyncSession,
    project: ProjectModel,
    users: List[UserModel],
):
    users_ids = [u.id for u in users]
    await session.execute(
        delete(MemberModel).where(
            MemberModel.project_id == project.id, MemberModel.user_id.in_(users_ids)
        )
    )


async def list_user_project_models(
    session: AsyncSession,
    user: UserModel,
) -> List[ProjectModel]:
    res = await session.execute(
        select(ProjectModel).where(
            MemberModel.project_id == ProjectModel.id,
            MemberModel.user_id == user.id,
        )
    )
    return res.scalars().all()


async def list_project_models(
    session: AsyncSession,
) -> List[ProjectModel]:
    res = await session.execute(select(ProjectModel))
    return res.scalars().all()


async def get_project_model_by_name(
    session: AsyncSession,
    project_name: str,
) -> Optional[ProjectModel]:
    res = await session.execute(select(ProjectModel).where(ProjectModel.name == project_name))
    return res.scalar()


async def create_project_model(session: AsyncSession, project_name: str) -> ProjectModel:
    private_bytes, public_bytes = await run_async(
        generate_rsa_key_pair_bytes, f"{project_name}@dstack"
    )
    project = ProjectModel(
        id=uuid.uuid4(),
        name=project_name,
        ssh_private_key=private_bytes.decode(),
        ssh_public_key=public_bytes.decode(),
    )
    session.add(project)
    await session.commit()
    return project


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
        config_info = configurator.get_config_info(model=b, include_creds=False)
        backend_info = BackendInfo(
            name=b.type,
            config=config_info,
        )
        backends.append(backend_info)
    return Project(
        project_id=project_model.id,
        project_name=project_model.name,
        backends=backends,
        members=members,
    )


def _is_project_admin(
    user: UserModel,
    project: ProjectModel,
) -> bool:
    for m in project.members:
        if user.id == m.user_id:
            if m.project_role == ProjectRole.ADMIN:
                return True
    return False
