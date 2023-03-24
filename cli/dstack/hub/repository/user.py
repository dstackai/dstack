import os
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Role, User
from dstack.hub.repository.role import RoleManager


class UserManager:
    @staticmethod
    async def create_admin(external_session=None) -> User:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        role = await RoleManager.get_or_create(name="admin", external_session=_session)
        admin_user = User(
            name="admin",
            token=os.getenv("DSTACK_HUB_ADMIN_TOKEN") or str(uuid.uuid4()),
            project_role=role,
        )
        await UserManager.save(admin_user, external_session=_session)
        if external_session is None:
            await _session.close()
        return admin_user

    @staticmethod
    async def get_user_by_name(name: str, external_session=None) -> Optional[User]:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(
            select(User).where(User.name == name).options(selectinload(User.project_role))
        )
        user = query.scalars().unique().first()
        if external_session is None:
            await _session.close()
        if user is None:
            return None
        return user

    @staticmethod
    async def get_user_by_token(token: str, external_session=None) -> Optional[User]:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(
            select(User).where(User.token == token).options(selectinload(User.project_role))
        )
        user = query.scalars().unique().first()
        if external_session is None:
            await _session.close()
        if user is None:
            return None
        return user

    @staticmethod
    async def get_user_list(external_session=None) -> List[User]:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(select(User).options(selectinload(User.project_role)))
        users = query.scalars().unique().all()
        if external_session is None:
            await _session.close()
        return users

    @staticmethod
    async def save(user: User, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        _session.add(user)
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def remove(user: User, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        await _session.delete(user)
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def scope(user: User, scope: str, external_session=None) -> bool:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        if external_session is None:
            await _session.close()
        return True

    @staticmethod
    async def create(name: str, role: str, external_session=None) -> User:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        role = await RoleManager.get_or_create(name=role, external_session=_session)
        admin_user = User(name=name, token=str(uuid.uuid4()), project_role=role)
        await UserManager.save(admin_user, external_session=_session)
        if external_session is None:
            await _session.close()
        return admin_user
