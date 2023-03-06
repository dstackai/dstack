import os
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Role, User
from dstack.hub.repository.role import RoleManager

session = Database.Session()


class UserManager:
    @staticmethod
    async def create_admin(external_session=None) -> User:
        _session = session
        if external_session is not None:
            _session = external_session
        role = await RoleManager.create(name="admin", external_session=_session)
        admin_user = User(
            name="admin",
            token=os.getenv("DSTACK_HUB_ADMIN_TOKEN") or str(uuid.uuid4()),
            hub_role=role,
        )
        await UserManager.save(admin_user, external_session=_session)
        return admin_user

    @staticmethod
    async def get_user_by_name(name: str, external_session=None) -> Optional[User]:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(
            select(User).where(User.name == name).options(selectinload(User.hub_role))
        )
        user = query.scalars().unique().first()
        if user is None:
            return None
        return user

    @staticmethod
    async def get_user_by_token(token: str, external_session=None) -> Optional[User]:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(
            select(User).where(User.token == token).options(selectinload(User.hub_role))
        )
        user = query.scalars().unique().first()
        if user is None:
            return None
        return user

    @staticmethod
    async def get_user_list(external_session=None) -> List[User]:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(select(User).options(selectinload(User.hub_role)))
        users = query.scalars().unique().all()
        return users

    @staticmethod
    async def save(user: User, external_session=None):
        _session = session
        if external_session is not None:
            _session = external_session
        _session.add(user)
        await _session.commit()

    @staticmethod
    async def remove(user: User, external_session=None):
        _session = session
        if external_session is not None:
            _session = external_session
        await _session.delete(user)
        await _session.commit()

    @staticmethod
    async def scope(user: User, scope: str, external_session=None) -> bool:
        _session = session
        if external_session is not None:
            _session = external_session
        return True

    @staticmethod
    async def create(name: str, role: str, external_session=None) -> User:
        _session = session
        if external_session is not None:
            _session = external_session
        role = await RoleManager.create(name=role, external_session=_session)
        admin_user = User(name=name, token=str(uuid.uuid4()), hub_role=role)
        await UserManager.save(admin_user, external_session=_session)
        return admin_user
