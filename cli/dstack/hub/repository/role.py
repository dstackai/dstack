import os
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from dstack.hub.db import Database
from dstack.hub.db.models import Role, User


class RoleManager:
    @staticmethod
    async def get_or_create(name: str, external_session=None) -> Role:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        role = await RoleManager.get_by_name(name=name, external_session=external_session)
        if role is None:
            await RoleManager.save(role=Role(name=name), external_session=external_session)
            role = await RoleManager.get_by_name(name=name, external_session=external_session)
        if external_session is None:
            await _session.close()
        return role

    @staticmethod
    async def get_by_name(name: str, external_session=None) -> Optional[Role]:
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        query = await _session.execute(select(Role).where(Role.name == name))
        role = query.scalars().first()
        if external_session is None:
            await _session.close()
        if role is None:
            return None
        return role

    @staticmethod
    async def save(role: Role, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        _session.add(role)
        await _session.commit()
        if external_session is None:
            await _session.close()

    @staticmethod
    async def remove(role: Role, external_session=None):
        if external_session is not None:
            _session = external_session
        else:
            _session = Database.Session()
        _session.delete(role)
        await _session.commit()
        if external_session is None:
            await _session.close()
