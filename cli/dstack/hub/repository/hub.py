from typing import Optional
from sqlalchemy import select
from dstack.hub.db import Database
from dstack.hub.db.models import User
from dstack.hub.models.user import UserInfo

session = Database.Session()


class HubManager:
    @staticmethod
    async def get_user_info(token: str) -> UserInfo:
        query = await session.execute(select(User).where(User.token == token))
        user = query.scalars().first()
        return UserInfo(user_name=user.name)

    @staticmethod
    async def get_user_by_name(name: str) -> Optional[User]:
        query = await session.execute(select(User).where(User.name == name))
        user = query.scalars().first()
        if user is None:
            return None
        return User(name=user.name, token=user.token)

    @staticmethod
    async def get_user_by_token(token: str) -> Optional[User]:
        query = await session.execute(select(User).where(User.token == token))
        user = query.scalars().first()
        if user is None:
            return None
        return User(name=user.name, token=user.token)

    @staticmethod
    async def save(user: User):
        session.add(user)
