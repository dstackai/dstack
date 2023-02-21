import uuid
from typing import List, Optional

from sqlalchemy import select

from dstack.hub.db import Database
from dstack.hub.db.models import Role, User

session = Database.Session()


class UserManager:
    @staticmethod
    async def get_user_by_name(name: str) -> Optional[User]:
        query = await session.execute(select(User).where(User.name == name))
        user = query.scalars().first()
        if user is None:
            return None
        return user

    @staticmethod
    async def get_user_by_token(token: str) -> Optional[User]:
        query = await session.execute(select(User).where(User.token == token))
        user = query.scalars().first()
        if user is None:
            return None
        return user

    @staticmethod
    async def get_user_list() -> List[User]:
        query = await session.execute(select(User))
        users = query.scalars().all()
        return users

    @staticmethod
    async def save(user: User):
        session.add(user)
        await session.commit()

    @staticmethod
    async def remove(user: User):
        session.delete(user)
        await session.commit()

    @staticmethod
    async def scope(user: User, scope: str) -> bool:
        return True

    @staticmethod
    async def create(name: str, role: str) -> User:
        query = await session.execute(select(Role).where(Role.name == role))
        role = query.scalars().first()
        if role is None:
            role = Role(name=name)
            session.add(role)
            await session.commit()
        user = User(name=name, token=str(uuid.uuid4()), roles=[role])
        await UserManager.save(user=user)
        return user
