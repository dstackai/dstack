import uuid
from typing import Awaitable, Callable, List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy import func as safunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import QueryableAttribute, joinedload, load_only

from dstack._internal.core.backends.configurators import get_configurator
from dstack._internal.core.backends.dstack.models import (
    DstackBackendConfig,
    DstackBaseBackendConfig,
)
from dstack._internal.core.backends.models import BackendInfo
from dstack._internal.core.errors import ForbiddenError, ResourceExistsError, ServerClientError
from dstack._internal.core.models.projects import Member, MemberPermissions, Project
from dstack._internal.core.models.users import GlobalRole, ProjectRole
from dstack._internal.server.models import MemberModel, ProjectModel, UserModel
from dstack._internal.server.schemas.projects import MemberSetting
from dstack._internal.server.services import users
from dstack._internal.server.services.backends import (
    get_backend_config_without_creds_from_backend_model,
)
from dstack._internal.server.services.permissions import get_default_permissions
from dstack._internal.server.settings import DEFAULT_PROJECT_NAME
from dstack._internal.utils.common import get_current_datetime, run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


async def get_or_create_default_project(
    session: AsyncSession,
    user: UserModel,
) -> Tuple[Project, bool]:
    default_project = await get_project_by_name(
        session=session,
        project_name=DEFAULT_PROJECT_NAME,
    )
    if default_project is not None:
        return default_project, False
    default_project = await create_project(
        session=session,
        user=user,
        project_name=DEFAULT_PROJECT_NAME,
    )
    return default_project, True


async def list_user_projects(
    session: AsyncSession,
    user: UserModel,
) -> List[Project]:
    """
    Returns projects where the user is a member or all projects for global admins.
    """
    projects = await list_user_project_models(
        session=session,
        user=user,
    )
    projects = sorted(projects, key=lambda p: p.created_at)
    return [
        project_model_to_project(p, include_backends=False, include_members=False)
        for p in projects
    ]


async def list_user_accessible_projects(
    session: AsyncSession,
    user: UserModel,
) -> List[Project]:
    """
    Returns all projects accessible to the user:
    - Projects where user is a member (public or private)
    - Public projects where user is NOT a member
    """
    if user.global_role == GlobalRole.ADMIN:
        projects = await list_project_models(session=session)
    else:
        member_projects = await list_member_project_models(session=session, user=user)
        public_projects = await list_public_non_member_project_models(session=session, user=user)
        projects = member_projects + public_projects

    projects = sorted(projects, key=lambda p: p.created_at)
    return [
        project_model_to_project(p, include_backends=False, include_members=False)
        for p in projects
    ]


async def list_projects(session: AsyncSession) -> List[Project]:
    projects = await list_project_models(session=session)
    return [
        project_model_to_project(p, include_backends=False, include_members=False)
        for p in projects
    ]


async def get_project_by_name(
    session: AsyncSession,
    project_name: str,
) -> Optional[Project]:
    project_model = await get_project_model_by_name(session=session, project_name=project_name)
    if project_model is None:
        return None
    return project_model_to_project(project_model)


async def create_project(
    session: AsyncSession,
    user: UserModel,
    project_name: str,
    is_public: bool = False,
) -> Project:
    user_permissions = users.get_user_permissions(user)
    if not user_permissions.can_create_projects:
        raise ForbiddenError("User cannot create projects")
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
        is_public=is_public,
    )
    await add_project_member(
        session=session,
        project=project,
        user=user,
        project_role=ProjectRole.ADMIN,
        member_num=0,
    )
    project_model = await get_project_model_by_name_or_error(
        session=session, project_name=project_name
    )
    for hook in _CREATE_PROJECT_HOOKS:
        await hook(session, project_model)
    # a hook may change project
    session.expire(project_model)
    project_model = await get_project_model_by_name_or_error(
        session=session, project_name=project_name
    )
    return project_model_to_project(project_model)


async def update_project(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    is_public: bool,
):
    """Update project visibility (public/private)."""
    project.is_public = is_public
    await session.commit()


async def delete_projects(
    session: AsyncSession,
    user: UserModel,
    projects_names: List[str],
):
    if user.global_role != GlobalRole.ADMIN:
        user_projects = await list_member_project_models(
            session=session, user=user, include_members=True
        )
        user_project_names = [p.name for p in user_projects]
        for project_name in projects_names:
            if project_name not in user_project_names:
                raise ForbiddenError()
        projects_to_delete = [p for p in user_projects if p.name in projects_names]
        for project in projects_to_delete:
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


async def set_project_members(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    members: List[MemberSetting],
):
    usernames = {m.username for m in members}
    if len(usernames) != len(members):
        raise ServerClientError("Cannot add same user multiple times")

    project = await get_project_model_by_name_or_error(
        session=session,
        project_name=project.name,
    )
    project_role = get_user_project_role(user=user, project=project)
    if user.global_role != GlobalRole.ADMIN and project_role == ProjectRole.MANAGER:
        new_admins_members = {
            (m.username, m.project_role) for m in members if m.project_role == ProjectRole.ADMIN
        }
        current_admins_members = {
            (m.user.name, m.project_role)
            for m in project.members
            if m.project_role == ProjectRole.ADMIN
        }
        if new_admins_members != current_admins_members:
            raise ForbiddenError("Access denied: changing project admins")
    # FIXME: potentially long write transaction
    # clear_project_members() issues DELETE without commit
    await clear_project_members(session=session, project=project)
    names = [m.username for m in members]
    res = await session.execute(
        select(UserModel).where((UserModel.name.in_(names)) | (UserModel.email.in_(names)))
    )
    users = res.scalars().all()
    username_to_user = {user.name: user for user in users}
    email_to_user = {user.email: user for user in users if user.email}
    for i, member in enumerate(members):
        user_to_add = username_to_user.get(member.username) or email_to_user.get(member.username)
        if user_to_add is None:
            continue
        await add_project_member(
            session=session,
            project=project,
            user=user_to_add,
            project_role=member.project_role,
            member_num=i,
            commit=False,
        )
    await session.commit()


async def add_project_members(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    members: List[MemberSetting],
):
    """Add multiple members to a project."""
    usernames = {m.username for m in members}
    if len(usernames) != len(members):
        raise ServerClientError("Cannot add same user multiple times")

    project = await get_project_model_by_name_or_error(
        session=session,
        project_name=project.name,
    )
    requesting_user_role = get_user_project_role(user=user, project=project)

    is_self_join_to_public = (
        len(members) == 1
        and project.is_public
        and (members[0].username == user.name or members[0].username == user.email)
        and requesting_user_role is None
    )

    if not is_self_join_to_public:
        if user.global_role != GlobalRole.ADMIN and requesting_user_role not in [
            ProjectRole.ADMIN,
            ProjectRole.MANAGER,
        ]:
            raise ForbiddenError("Access denied: insufficient permissions to add members")

        if user.global_role != GlobalRole.ADMIN and requesting_user_role == ProjectRole.MANAGER:
            for member in members:
                if member.project_role == ProjectRole.ADMIN:
                    raise ForbiddenError(
                        "Access denied: only global admins can add project admins"
                    )
    else:
        if members[0].project_role != ProjectRole.USER:
            raise ForbiddenError("Access denied: can only join public projects as user role")

    res = await session.execute(
        select(UserModel).where((UserModel.name.in_(usernames)) | (UserModel.email.in_(usernames)))
    )
    users_found = res.scalars().all()

    username_to_user = {user.name: user for user in users_found}
    email_to_user = {user.email: user for user in users_found if user.email}

    member_by_user_id = {m.user_id: m for m in project.members}

    for member_setting in members:
        user_to_add = username_to_user.get(member_setting.username) or email_to_user.get(
            member_setting.username
        )
        if user_to_add is None:
            raise ServerClientError(f"User not found: {member_setting.username}")

        if user_to_add.id in member_by_user_id:
            existing_member = member_by_user_id[user_to_add.id]
            if existing_member.project_role != member_setting.project_role:
                existing_member.project_role = member_setting.project_role
        else:
            await add_project_member(
                session=session,
                project=project,
                user=user_to_add,
                project_role=member_setting.project_role,
                member_num=None,
                commit=False,
            )

    await session.commit()


async def add_project_member(
    session: AsyncSession,
    project: ProjectModel,
    user: UserModel,
    project_role: ProjectRole,
    member_num: Optional[int] = None,
    commit: bool = True,
) -> MemberModel:
    member = MemberModel(
        user_id=user.id,
        project_id=project.id,
        project_role=project_role,
        member_num=member_num,
    )
    session.add(member)
    if commit:
        await session.commit()
    return member


async def clear_project_members(
    session: AsyncSession,
    project: ProjectModel,
):
    await session.execute(delete(MemberModel).where(MemberModel.project_id == project.id))


async def list_user_project_models(
    session: AsyncSession,
    user: UserModel,
    only_names: bool = False,
) -> List[ProjectModel]:
    load_only_attrs = []
    if only_names:
        load_only_attrs += [ProjectModel.id, ProjectModel.name]
    if user.global_role == GlobalRole.ADMIN:
        return await list_project_models(session=session, load_only_attrs=load_only_attrs)
    return await list_member_project_models(
        session=session, user=user, load_only_attrs=load_only_attrs
    )


async def list_member_project_models(
    session: AsyncSession,
    user: UserModel,
    include_members: bool = False,
    load_only_attrs: Optional[List[QueryableAttribute]] = None,
) -> List[ProjectModel]:
    """
    List project models for a user where they are a member.
    """
    options = []
    if include_members:
        options.append(joinedload(ProjectModel.members))
    if load_only_attrs:
        options.append(load_only(*load_only_attrs))
    res = await session.execute(
        select(ProjectModel)
        .where(
            MemberModel.project_id == ProjectModel.id,
            MemberModel.user_id == user.id,
            ProjectModel.deleted == False,
        )
        .options(*options)
    )
    return list(res.scalars().unique().all())


async def list_public_non_member_project_models(
    session: AsyncSession,
    user: UserModel,
) -> List[ProjectModel]:
    """
    List public project models where user is NOT a member.
    """
    res = await session.execute(
        select(ProjectModel).where(
            ProjectModel.deleted == False,
            ProjectModel.is_public == True,
            ProjectModel.id.notin_(
                select(MemberModel.project_id).where(MemberModel.user_id == user.id)
            ),
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
    load_only_attrs: Optional[List[QueryableAttribute]] = None,
) -> List[ProjectModel]:
    options = []
    if load_only_attrs:
        options.append(load_only(*load_only_attrs))
    res = await session.execute(
        select(ProjectModel).where(ProjectModel.deleted == False).options(*options)
    )
    return list(res.scalars().all())


# TODO: Do not load ProjectModel.backends and ProjectModel.members by default when getting project


async def get_project_model_by_name(
    session: AsyncSession, project_name: str, ignore_case: bool = True
) -> Optional[ProjectModel]:
    filters = [ProjectModel.deleted == False]
    if ignore_case:
        filters.append(safunc.lower(ProjectModel.name) == safunc.lower(project_name))
    else:
        filters.append(ProjectModel.name == project_name)
    res = await session.execute(
        select(ProjectModel)
        .where(*filters)
        .options(joinedload(ProjectModel.backends))
        .options(joinedload(ProjectModel.members))
    )
    return res.unique().scalar()


async def get_project_model_by_name_or_error(
    session: AsyncSession,
    project_name: str,
) -> ProjectModel:
    res = await session.execute(
        select(ProjectModel)
        .where(
            ProjectModel.name == project_name,
            ProjectModel.deleted == False,
        )
        .options(joinedload(ProjectModel.backends))
        .options(joinedload(ProjectModel.members))
    )
    return res.unique().scalar_one()


async def get_project_model_by_id_or_error(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> ProjectModel:
    res = await session.execute(
        select(ProjectModel)
        .where(
            ProjectModel.id == project_id,
            ProjectModel.deleted == False,
        )
        .options(joinedload(ProjectModel.backends))
        .options(joinedload(ProjectModel.members))
    )
    return res.unique().scalar_one()


async def create_project_model(
    session: AsyncSession, owner: UserModel, project_name: str, is_public: bool = False
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
        is_public=is_public,
    )
    session.add(project)
    await session.commit()
    return project


def get_user_project_role(user: UserModel, project: ProjectModel) -> Optional[ProjectRole]:
    for member in project.members:
        if member.user_id == user.id:
            return member.project_role
    return None


def get_member(user: UserModel, project: ProjectModel) -> Optional[MemberModel]:
    for member in project.members:
        if member.user_id == user.id:
            return member
    return None


def project_model_to_project(
    project_model: ProjectModel,
    include_backends: bool = True,
    include_members: bool = True,
) -> Project:
    members = []
    if include_members:
        for m in project_model.members:
            members.append(
                Member(
                    user=users.user_model_to_user(m.user),
                    project_role=m.project_role,
                    permissions=get_member_permissions(m),
                )
            )
    backends = []
    if include_backends:
        for b in project_model.backends:
            configurator = get_configurator(b.type)
            if configurator is None:
                logger.warning("Configurator for backend %s not found", b.type)
                continue
            if not b.auth.decrypted:
                logger.warning(
                    "Failed to decrypt creds for %s backend. Backend will be ignored.",
                    b.type.value,
                )
                continue
            backend_config = get_backend_config_without_creds_from_backend_model(configurator, b)
            if isinstance(backend_config, DstackBackendConfig):
                for backend_type in backend_config.base_backends:
                    backends.append(
                        BackendInfo(
                            name=backend_type,
                            config=DstackBaseBackendConfig(type=backend_type),
                        )
                    )
            else:
                backends.append(
                    BackendInfo(
                        name=b.type,
                        config=backend_config,
                    )
                )
    return Project(
        project_id=project_model.id,
        project_name=project_model.name,
        owner=users.user_model_to_user(project_model.owner),
        created_at=project_model.created_at,
        backends=backends,
        members=members,
        is_public=project_model.is_public,
    )


def get_member_permissions(member_model: MemberModel) -> MemberPermissions:
    default_permissions = get_default_permissions()
    user_model = member_model.user
    can_manage_ssh_fleets = True
    if not default_permissions.allow_non_admins_manage_ssh_fleets:
        if (
            user_model.global_role != GlobalRole.ADMIN
            and member_model.project_role != ProjectRole.ADMIN
        ):
            can_manage_ssh_fleets = False
    return MemberPermissions(
        can_manage_ssh_fleets=can_manage_ssh_fleets,
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
    if user.id == project.owner_id:
        return True

    for m in project.members:
        if user.id == m.user_id:
            if m.project_role == ProjectRole.ADMIN:
                return True
    return False


async def remove_project_members(
    session: AsyncSession,
    user: UserModel,
    project: ProjectModel,
    usernames: List[str],
):
    """Remove multiple members from a project."""
    project = await get_project_model_by_name_or_error(
        session=session,
        project_name=project.name,
    )
    requesting_user_role = get_user_project_role(user=user, project=project)

    is_self_leave = (
        len(usernames) == 1
        and (usernames[0] == user.name or usernames[0] == user.email)
        and requesting_user_role is not None
    )

    if not is_self_leave:
        if user.global_role != GlobalRole.ADMIN and requesting_user_role not in [
            ProjectRole.ADMIN,
            ProjectRole.MANAGER,
        ]:
            raise ForbiddenError("Access denied: insufficient permissions to remove members")

    res = await session.execute(
        select(UserModel).where((UserModel.name.in_(usernames)) | (UserModel.email.in_(usernames)))
    )
    users_found = res.scalars().all()

    username_to_user = {user.name: user for user in users_found}
    email_to_user = {user.email: user for user in users_found if user.email}

    member_by_user_id = {m.user_id: m for m in project.members}

    members_to_remove = []
    admin_removals = 0

    for username in usernames:
        user_to_remove = username_to_user.get(username) or email_to_user.get(username)
        if user_to_remove is None:
            raise ServerClientError(f"User not found: {username}")

        if user_to_remove.id not in member_by_user_id:
            raise ServerClientError(f"User is not a member of this project: {username}")

        member_to_remove = member_by_user_id[user_to_remove.id]

        if member_to_remove.project_role == ProjectRole.ADMIN:
            if is_self_leave:
                total_admins = sum(
                    1 for member in project.members if member.project_role == ProjectRole.ADMIN
                )
                if total_admins <= 1:
                    raise ServerClientError("Cannot leave project: you are the last admin")
            else:
                if user.global_role != GlobalRole.ADMIN:
                    raise ForbiddenError(
                        f"Access denied: only global admins can remove project admins (user: {username})"
                    )
            admin_removals += 1

        members_to_remove.append(member_to_remove)

    if not is_self_leave:
        total_admins = sum(
            1 for member in project.members if member.project_role == ProjectRole.ADMIN
        )
        if admin_removals >= total_admins:
            raise ServerClientError("Cannot remove all project admins")

    for member in members_to_remove:
        await session.delete(member)

    await session.commit()
