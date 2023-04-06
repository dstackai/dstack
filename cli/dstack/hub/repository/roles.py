from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack.hub.db import reuse_or_make_session
from dstack.hub.db.models import Role


class RoleManager:
    @staticmethod
    @reuse_or_make_session
    async def get_or_create(name: str, session: Optional[AsyncSession] = None) -> Role:
        role = await RoleManager.get_by_name(name=name, session=session)
        if role is None:
            await RoleManager.save(role=Role(name=name), session=session)
            role = await RoleManager.get_by_name(name=name, session=session)
        return role

    @staticmethod
    @reuse_or_make_session
    async def get_by_name(name: str, session: Optional[AsyncSession] = None) -> Optional[Role]:
        query = await session.execute(select(Role).where(Role.name == name))
        role = query.scalars().first()
        if session is None:
            await session.close()
        return role

    @staticmethod
    @reuse_or_make_session
    async def save(role: Role, session: Optional[AsyncSession] = None):
        session.add(role)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def remove(role: Role, session: Optional[AsyncSession] = None):
        session.delete(role)
        await session.commit()
