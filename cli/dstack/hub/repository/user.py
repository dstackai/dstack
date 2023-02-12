from typing import Optional

from sqlalchemy import select

from dstack.hub.db import Database
from dstack.hub.db.models import User

session = Database.Session()


class UserManager:
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
        await session.commit()

    @staticmethod
    async def scope(user: User, scope: str) -> bool:
        return True
