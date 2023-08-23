import json
from typing import List, Optional, Union

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack._internal.hub.db import reuse_or_make_session
from dstack._internal.hub.db.models import Backend
from dstack._internal.hub.db.models import Member as DBMember
from dstack._internal.hub.db.models import Project, User
from dstack._internal.hub.schemas import (
    AnyBackendConfigWithCreds,
    BackendInfo,
    BackendInfoWithCreds,
    Member,
    ProjectInfo,
)
from dstack._internal.hub.security.utils import ROLE_ADMIN
from dstack._internal.hub.services.backends import get_configurator
from dstack._internal.hub.utils.common import run_async
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes


class ProjectManager:
    @staticmethod
    async def get_project_info(project: Project) -> Optional[ProjectInfo]:
        return await _project_to_project_info(project=project)

    @staticmethod
    @reuse_or_make_session
    async def create(
        user: User,
        project_name: str,
        members: List[Member],
        session: Optional[AsyncSession] = None,
    ) -> Project:
        private_bytes, public_bytes = await run_async(
            generate_rsa_key_pair_bytes, f"{project_name}@dstack"
        )
        project = Project(
            name=project_name,
            ssh_private_key=private_bytes.decode(),
            ssh_public_key=public_bytes.decode(),
        )
        await ProjectManager._create(project, session=session)
        await ProjectManager._add_member(
            project=project,
            member=Member(user_name=user.name, project_role=ROLE_ADMIN),
            session=session,
        )
        return project

    @staticmethod
    @reuse_or_make_session
    async def list_project_info(session: Optional[AsyncSession] = None) -> List[ProjectInfo]:
        query = await session.execute(select(Project).options(selectinload(Project.members)))
        projects = query.scalars().unique().all()
        projects_info = []
        for project in projects:
            project_info = await _project_to_project_info(project=project)
            if project_info is not None:
                projects_info.append(project_info)
        return projects_info

    @staticmethod
    @reuse_or_make_session
    async def get(name: str, session: Optional[AsyncSession] = None) -> Optional[Project]:
        query = await session.execute(
            select(Project).options(selectinload(Project.members)).where(Project.name == name)
        )
        project = query.scalars().unique().first()
        return project

    @staticmethod
    @reuse_or_make_session
    async def list(session: Optional[AsyncSession] = None) -> List[Project]:
        query = await session.execute(select(Project).options(selectinload(Project.members)))
        projects = query.scalars().unique().all()
        return projects

    @staticmethod
    @reuse_or_make_session
    async def delete(project_name: str, session: Optional[AsyncSession] = None):
        await session.execute(delete(Project).where(Project.name == project_name))
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def set_default_gateway(
        project_name: str, default_gateway: Optional[str], session: Optional[AsyncSession] = None
    ):
        await session.execute(
            update(Project)
            .where(Project.name == project_name)
            .values(default_gateway=default_gateway)
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def get_member(
        user: User, project: Project, session: Optional[AsyncSession] = None
    ) -> Optional[DBMember]:
        query = await session.execute(
            select(DBMember).where(
                DBMember.project_name == project.name, DBMember.user_name == user.name
            )
        )
        return query.scalars().unique().first()

    @staticmethod
    @reuse_or_make_session
    async def set_members(
        project: Project, members: List[Member], session: Optional[AsyncSession] = None
    ) -> Optional[DBMember]:
        await ProjectManager._clear_member(project, session=session)
        for member in members:
            await ProjectManager._add_member(project=project, member=member, session=session)

    @staticmethod
    @reuse_or_make_session
    async def list_backend_infos(
        project: Project, session: Optional[AsyncSession] = None
    ) -> List[BackendInfo]:
        backend_infos = []
        for backend in project.backends:
            backend_info = await _backend_to_backend_info(backend=backend)
            if backend_info is not None:
                backend_infos.append(backend_info)
        return backend_infos

    @staticmethod
    @reuse_or_make_session
    async def get_backend_info(
        project: Project, backend_name: str, session: Optional[AsyncSession] = None
    ) -> Optional[BackendInfoWithCreds]:
        backend = await ProjectManager._get_backend(
            project=project, backend_name=backend_name, session=session
        )
        backend_info = await _backend_to_backend_info(backend=backend, include_creds=True)
        return backend_info

    @staticmethod
    @reuse_or_make_session
    async def get_backend(
        project: Project, backend_name: str, session: Optional[AsyncSession] = None
    ) -> Optional[Backend]:
        backend = await ProjectManager._get_backend(
            project=project, backend_name=backend_name, session=session
        )
        return backend

    @staticmethod
    @reuse_or_make_session
    async def create_backend(
        project: Project,
        backend_config: AnyBackendConfigWithCreds,
        session: Optional[AsyncSession] = None,
    ):
        backend = await _backend_config_to_backend(
            project_name=project.name, backend_config=backend_config
        )
        if backend is None:
            return
        await ProjectManager._create_backend(backend=backend, session=session)

    @staticmethod
    @reuse_or_make_session
    async def update_backend(
        project: Project,
        backend_config: AnyBackendConfigWithCreds,
        session: Optional[AsyncSession] = None,
    ):
        backend = await _backend_config_to_backend(
            project_name=project.name, backend_config=backend_config
        )
        await ProjectManager._update_backend(backend=backend, session=session)

    @staticmethod
    @reuse_or_make_session
    async def delete_backend(
        project: Project, backend_name: str, session: Optional[AsyncSession] = None
    ):
        await session.execute(
            delete(Backend).where(
                Backend.project_name == project.name,
                Backend.name == backend_name,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _create(project: Project, session: Optional[AsyncSession] = None):
        session.add(project)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _add_member(
        project: Project, member: Member, session: Optional[AsyncSession] = None
    ):
        session.add(
            DBMember(
                project_name=project.name,
                user_name=member.user_name,
                project_role=member.project_role,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _clear_member(project: Project, session: Optional[AsyncSession] = None):
        await session.execute(delete(DBMember).where(DBMember.project_name == project.name))
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _get_backend(
        project: Project, backend_name: str, session: Optional[AsyncSession] = None
    ) -> Optional[Backend]:
        query = await session.execute(
            select(Backend).where(
                Backend.project_name == project.name, Backend.name == backend_name
            )
        )
        return query.scalars().unique().first()

    @staticmethod
    @reuse_or_make_session
    async def _create_backend(backend: Backend, session: Optional[AsyncSession] = None):
        session.add(backend)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _update_backend(backend: Backend, session: Optional[AsyncSession] = None):
        await session.execute(
            update(Backend)
            .where(Backend.project_name == backend.project_name, Backend.name == backend.name)
            .values(
                config=backend.config,
                auth=backend.auth,
            )
        )
        await session.commit()


async def _backend_config_to_backend(
    project_name: str, backend_config: AnyBackendConfigWithCreds
) -> Optional[Backend]:
    backend = Backend(
        project_name=project_name,
        name=backend_config.type,
        type=backend_config.type,
    )
    configurator = get_configurator(backend_config.type)
    if configurator is None:
        return None
    config, auth = await run_async(configurator.create_backend, project_name, backend_config)
    backend.config = json.dumps(config)
    backend.auth = json.dumps(auth)
    return backend


async def _backend_to_backend_info(
    backend: Backend, include_creds: bool = False
) -> Union[BackendInfo, BackendInfoWithCreds, None]:
    configurator = get_configurator(backend.type)
    if configurator is None:
        return None
    backend_config = configurator.get_backend_config(backend, include_creds=include_creds)
    if include_creds:
        return BackendInfoWithCreds(
            name=backend.name,
            config=backend_config,
        )
    return BackendInfo(
        name=backend.name,
        config=backend_config,
    )


async def _project_to_project_info(project: Project) -> Optional[ProjectInfo]:
    members = []
    backend_infos = []
    for member in project.members:
        members.append(
            Member(
                user_name=member.user_name,
                project_role=member.project_role,
            )
        )
    for backend in project.backends:
        backend_info = await _backend_to_backend_info(backend=backend, include_creds=False)
        if backend_info is None:
            continue
        backend_infos.append(backend_info)
    return ProjectInfo(project_name=project.name, backends=backend_infos, members=members)
