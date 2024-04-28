import uuid
from typing import Awaitable, Callable, List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy import func as safunc
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ForbiddenError, ResourceExistsError, ServerClientError
from dstack._internal.core.models.backends import BackendInfo
from dstack._internal.core.models.backends.dstack import (
    DstackBaseBackendConfigInfo,
    DstackConfigInfo,
)
from dstack._internal.core.models.common import is_core_model_instance
from dstack._internal.core.models.projects import Member, Project
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import MemberModel, ProjectModel, UserModel
from dstack._internal.server.schemas.projects import MemberSetting
from dstack._internal.server.services import users
from dstack._internal.server.services.backends import get_configurator
from dstack._internal.server.settings import DEFAULT_PROJECT_NAME
from dstack._internal.server.utils.common import run_async
from dstack._internal.utils.common import get_current_datetime
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


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
    if user.global_role == GlobalRole.ADMIN:
        projects = await list_project_models(session=session)
    else:
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
    project = await get_project_model_by_name(
        session=session, project_name=project_name, ignore_case=True
    )
    if project is not None:
        raise ResourceExistsError()
    await _check_projects_quota(session=session, user=user)
    project = await create_project_model(
        session=session,
        owner=user,
        project_name=project_name,
    )
    await add_project_member(
        session=session,
        project=project,
        user=user,
        project_role=ProjectRole.ADMIN,
    )
    project_model = await get_project_model_by_name_or_error(
        session=session, project_name=project_name
    )
    for hook in _CREATE_PROJECT_HOOKS:
        await hook(session, project_model)
    await session.refresh(project_model)  # a hook may change project
    return project_model_to_project(project_model)


async def delete_projects(
    session: AsyncSession,
    user: UserModel,
    projects_names: List[str],
):
    if user.global_role != GlobalRole.ADMIN:
        user_projects = await list_user_project_models(session=session, user=user)
        user_project_names = [p.name for p in user_projects]
        for project_name in projects_names:
            if project_name not in user_project_names:
                raise ForbiddenError()
        for project in user_projects:
            if not _is_project_admin(user=user, project=project):
                raise ForbiddenError()
        if all(name in projects_names for name in user_project_names):
            raise ServerClientError("Cannot delete the only project")
    timestamp = str(int(get_current_datetime().timestamp()))
    new_project_name = "_deleted_" + timestamp + ProjectModel.name
    await session.execute(
        update(ProjectModel)
        .where(ProjectModel.name.in_(projects_names))
        .values(
            deleted=True,
            name=new_project_name,
        )
    )
    await session.commit()


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
    await clear_project_members(session=session, project=project)
    usernames = [m.username for m in members]
    res = await session.execute(select(UserModel).where(UserModel.name.in_(usernames)))
    users = res.scalars().all()
    username_to_user = {user.name: user for user in users}
    for member in members:
        user = username_to_user.get(member.username)
        if user is None:
            continue
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
):
    await session.execute(delete(MemberModel).where(MemberModel.project_id == project.id))


async def list_user_project_models(
    session: AsyncSession,
    user: UserModel,
) -> List[ProjectModel]:
    res = await session.execute(
        select(ProjectModel).where(
            MemberModel.project_id == ProjectModel.id,
            MemberModel.user_id == user.id,
            ProjectModel.deleted == False,
        )
    )
    return list(res.scalars().all())


async def list_user_owned_project_models(
    session: AsyncSession, user: UserModel, include_deleted: bool = False
) -> List[ProjectModel]:
    filters = [
        ProjectModel.owner_id == user.id,
        ProjectModel.deleted == False,
    ]
    if not include_deleted:
        filters.append(ProjectModel.deleted == False)
    res = await session.execute(select(ProjectModel).where(*filters))
    return list(res.scalars().all())


async def list_project_models(
    session: AsyncSession,
) -> List[ProjectModel]:
    res = await session.execute(
        select(ProjectModel).where(ProjectModel.deleted == False),
    )
    return list(res.scalars().all())


async def get_project_model_by_name(
    session: AsyncSession, project_name: str, ignore_case: bool = True
) -> Optional[ProjectModel]:
    filters = [ProjectModel.deleted == False]
    if ignore_case:
        filters.append(safunc.lower(ProjectModel.name) == safunc.lower(project_name))
    else:
        filters.append(ProjectModel.name == project_name)
    res = await session.execute(select(ProjectModel).where(*filters))
    return res.scalar()


async def get_project_model_by_name_or_error(
    session: AsyncSession,
    project_name: str,
) -> ProjectModel:
    res = await session.execute(
        select(ProjectModel).where(
            ProjectModel.name == project_name,
            ProjectModel.deleted == False,
        )
    )
    return res.scalar_one()


async def get_project_model_by_id_or_error(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> ProjectModel:
    res = await session.execute(
        select(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.deleted == False,
        )
    )
    return res.scalar_one()


async def create_project_model(
    session: AsyncSession, owner: UserModel, project_name: str
) -> ProjectModel:
    private_bytes, public_bytes = await run_async(
        generate_rsa_key_pair_bytes, f"{project_name}@dstack"
    )
    project = ProjectModel(
        id=uuid.uuid4(),
        owner_id=owner.id,
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
        if configurator is None:
            logger.warning("Configurator for backend %s not found", b.type)
            continue
        config_info = configurator.get_config_info(model=b, include_creds=False)
        if is_core_model_instance(config_info, DstackConfigInfo):
            for backend_type in config_info.base_backends:
                backends.append(
                    BackendInfo(
                        name=backend_type, config=DstackBaseBackendConfigInfo(type=backend_type)
                    )
                )
        else:
            backends.append(
                BackendInfo(
                    name=b.type,
                    config=config_info,
                )
            )
    return Project(
        project_id=project_model.id,
        project_name=project_model.name,
        owner=users.user_model_to_user(project_model.owner),
        backends=backends,
        members=members,
    )


_CREATE_PROJECT_HOOKS = []


def register_create_project_hook(func: Callable[[AsyncSession, ProjectModel], Awaitable[None]]):
    _CREATE_PROJECT_HOOKS.append(func)


async def _check_projects_quota(session: AsyncSession, user: UserModel):
    if user.global_role == GlobalRole.ADMIN:
        return
    owned_projects = await list_user_owned_project_models(session=session, user=user)
    if len(owned_projects) >= user.projects_quota:
        raise ServerClientError("User project quota exceeded")


def _is_project_admin(
    user: UserModel,
    project: ProjectModel,
) -> bool:
    for m in project.members:
        if user.id == m.user_id:
            if m.project_role == ProjectRole.ADMIN:
                return True
    return False
