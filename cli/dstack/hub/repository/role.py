import os
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Role, User

session = Database.Session()


class RoleManager:
    @staticmethod
    async def create(name: str, external_session=None) -> Role:
        _session = session
        if external_session is not None:
            _session = external_session
        role = await RoleManager.get_by_name(name=name, external_session=external_session)
        if role is None:
            await RoleManager.save(role=Role(name=name), external_session=external_session)
            role = await RoleManager.get_by_name(name=name, external_session=external_session)
        return role

    @staticmethod
    async def get_by_name(name: str, external_session=None) -> Optional[Role]:
        _session = session
        if external_session is not None:
            _session = external_session
        query = await _session.execute(select(Role).where(Role.name == name))
        role = query.scalars().first()
        if role is None:
            return None
        return role

    @staticmethod
    async def save(role: Role, external_session=None):
        _session = session
        if external_session is not None:
            _session = external_session
        _session.add(role)
        await _session.commit()

    @staticmethod
    async def remove(role: Role, external_session=None):
        _session = session
        if external_session is not None:
            _session = external_session
        _session.delete(role)
        await _session.commit()
