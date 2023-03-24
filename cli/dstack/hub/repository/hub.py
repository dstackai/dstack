import json
from typing import List

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Member as MemberDB
from dstack.hub.db.models import Project as ProjectDB
from dstack.hub.models import Member, ProjectInfo
from dstack.hub.repository.role import RoleManager
from dstack.hub.util import project2info


class ProjectManager:
    @staticmethod
    async def get_info(name: str, external_session=None) -> ProjectInfo:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(
            select(ProjectDB)
            .options(selectinload(ProjectDB.members))
            .where(ProjectDB.name == name)
        )
        project = query.scalars().unique().first()
        project_info = project2info(project=project)
        if external_session is None:
            await _session.close()
        return project_info

    @staticmethod
    async def get(name: str, external_session=None) -> ProjectDB:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(
            select(ProjectDB)
            .options(selectinload(ProjectDB.members))
            .where(ProjectDB.name == name)
        )
        project = query.scalars().unique().first()
        if external_session is None:
            await _session.close()
        return project

    @staticmethod
    async def save(project: ProjectDB, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        _session.add(project)
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def remove(project: ProjectDB, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        await _session.execute(delete(ProjectDB).where(ProjectDB.name == project.name))
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def list_info(external_session=None) -> List[ProjectInfo]:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(select(ProjectDB).options(selectinload(ProjectDB.members)))
        projects = query.scalars().unique().all()
        projects_info = []
        for project in projects:
            projects_info.append(project2info(project=project))
        if external_session is None:
            await _session.close()
        return projects_info

    @staticmethod
    async def add_member(project: ProjectDB, member: Member, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        role = await RoleManager.get_or_create(name=member.project_role, external_session=_session)
        _session.add(
            MemberDB(project_name=project.name, user_name=member.user_name, role_id=role.id)
        )
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def clear_member(project: ProjectDB, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        await _session.execute(delete(MemberDB).where(MemberDB.project_name == project.name))
        await _session.commit()
        if external_session is None:
            await _session.close()
