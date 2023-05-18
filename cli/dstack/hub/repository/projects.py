import asyncio
import json
from typing import List, Optional, Union

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from dstack.hub.db import reuse_or_make_session
from dstack.hub.db.models import Member as MemberDB
from dstack.hub.db.models import Project, User
from dstack.hub.models import LocalProjectConfig, Member, ProjectInfo, ProjectInfoWithCreds
from dstack.hub.security.utils import ROLE_ADMIN
from dstack.hub.services.backends import get_configurator


class ProjectManager:
    @staticmethod
    async def get_project_info_with_creds(project: Project) -> Optional[ProjectInfoWithCreds]:
        return _project2info(project=project, include_creds=True)

    @staticmethod
    async def get_project_info(project: Project) -> Optional[ProjectInfo]:
        return _project2info(project=project, include_creds=False)

    @staticmethod
    @reuse_or_make_session
    async def create_project_from_info(
        user: User, project_info: ProjectInfoWithCreds, session: Optional[AsyncSession] = None
    ):
        project = await _info2project(project_info)
        await ProjectManager.create(project, session=session)
        await ProjectManager._add_member(
            project, Member(user_name=user.name, project_role=ROLE_ADMIN)
        )

    @staticmethod
    @reuse_or_make_session
    async def create_local_project(
        user: User, project_name: str, session: Optional[AsyncSession] = None
    ):
        project_info = ProjectInfoWithCreds(
            project_name=project_name, backend=LocalProjectConfig()
        )
        await ProjectManager.create_project_from_info(
            user=user, project_info=project_info, session=session
        )

    @staticmethod
    async def update_project_from_info(
        project_info: ProjectInfoWithCreds, session: Optional[AsyncSession] = None
    ):
        project = await _info2project(project_info)
        await ProjectManager.update(project, session=session)

    @staticmethod
    @reuse_or_make_session
    async def list_project_info(session: Optional[AsyncSession] = None) -> List[ProjectInfo]:
        query = await session.execute(select(Project).options(selectinload(Project.members)))
        projects = query.scalars().unique().all()
        projects_info = []
        for project in projects:
            project_info = _project2info(project=project)
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
    async def create(project: Project, session: Optional[AsyncSession] = None):
        session.add(project)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def update(project: Project, session: Optional[AsyncSession] = None):
        await session.execute(
            update(Project)
            .where(Project.name == project.name)
            .values(
                backend=project.backend,
                config=project.config,
                auth=project.auth,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def delete(project_name: str, session: Optional[AsyncSession] = None):
        await session.execute(delete(Project).where(Project.name == project_name))
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def get_member(
        user: User, project: Project, session: Optional[AsyncSession] = None
    ) -> Optional[MemberDB]:
        query = await session.execute(
            select(MemberDB).where(
                MemberDB.project_name == project.name, MemberDB.user_name == user.name
            )
        )
        return query.scalars().unique().first()

    @staticmethod
    @reuse_or_make_session
    async def set_members(
        project: Project, members: List[Member], session: Optional[AsyncSession] = None
    ) -> Optional[MemberDB]:
        await ProjectManager._clear_member(project, session=session)
        for member in members:
            await ProjectManager._add_member(project=project, member=member)

    @staticmethod
    @reuse_or_make_session
    async def _add_member(
        project: Project, member: Member, session: Optional[AsyncSession] = None
    ):
        session.add(
            MemberDB(
                project_name=project.name,
                user_name=member.user_name,
                project_role=member.project_role,
            )
        )
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def _clear_member(project: Project, session: Optional[AsyncSession] = None):
        await session.execute(delete(MemberDB).where(MemberDB.project_name == project.name))
        await session.commit()


async def _info2project(project_info: ProjectInfoWithCreds) -> Project:
    project_info.backend = project_info.backend.__root__
    project = Project(
        name=project_info.project_name,
        backend=project_info.backend.type,
    )
    configurator = get_configurator(project.backend)
    config, auth = await asyncio.get_running_loop().run_in_executor(
        None, configurator.create_config_auth_data_from_project_config, project_info.backend
    )
    project.config = json.dumps(config)
    project.auth = json.dumps(auth)
    return project


def _project2info(
    project: Project, include_creds: bool = False
) -> Union[ProjectInfo, ProjectInfoWithCreds, None]:
    members = []
    for member in project.members:
        members.append(
            Member(
                user_name=member.user_name,
                project_role=member.project_role,
            )
        )
    configurator = get_configurator(project.backend)
    if configurator is None:
        return None
    backend = configurator.get_project_config_from_project(project, include_creds=include_creds)
    if include_creds:
        return ProjectInfoWithCreds(project_name=project.name, backend=backend, members=members)
    return ProjectInfo(project_name=project.name, backend=backend, members=members)
