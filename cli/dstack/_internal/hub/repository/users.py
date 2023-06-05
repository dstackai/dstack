import os
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.hub.db import reuse_or_make_session
from dstack._internal.hub.db.models import User
from dstack._internal.hub.security.utils import ROLE_ADMIN


class UserManager:
    @staticmethod
    @reuse_or_make_session
    async def create_admin(session: Optional[AsyncSession] = None) -> User:
        admin_user = User(
            name="admin",
            token=os.getenv("DSTACK_HUB_ADMIN_TOKEN") or str(uuid.uuid4()),
            global_role=ROLE_ADMIN,
        )
        await UserManager.save(admin_user, session=session)
        return admin_user

    @staticmethod
    @reuse_or_make_session
    async def get_user_by_name(
        name: str, session: Optional[AsyncSession] = None
    ) -> Optional[User]:
        query = await session.execute(select(User).where(User.name == name))
        user = query.scalars().unique().first()
        return user

    @staticmethod
    @reuse_or_make_session
    async def get_user_by_token(
        token: str, session: Optional[AsyncSession] = None
    ) -> Optional[User]:
        query = await session.execute(select(User).where(User.token == token))
        user = query.scalars().unique().first()
        return user

    @staticmethod
    @reuse_or_make_session
    async def get_user_list(session: Optional[AsyncSession] = None) -> List[User]:
        query = await session.execute(select(User))
        users = query.scalars().unique().all()
        return users

    @staticmethod
    @reuse_or_make_session
    async def save(user: User, session: Optional[AsyncSession] = None):
        session.add(user)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def remove(user: User, session: Optional[AsyncSession] = None):
        await session.delete(user)
        await session.commit()

    @staticmethod
    @reuse_or_make_session
    async def scope(user: User, scope: str, session: Optional[AsyncSession] = None) -> bool:
        return True

    @staticmethod
    @reuse_or_make_session
    async def create(name: str, global_role: str, session: Optional[AsyncSession] = None) -> User:
        user = User(name=name, token=str(uuid.uuid4()), global_role=global_role)
        await UserManager.save(user, session=session)
        return user
