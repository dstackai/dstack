from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.users import GlobalRole, User, UserTokenCreds, UserWithCreds
from dstack._internal.server.models import UserModel


async def list_users(
    session: AsyncSession,
) -> List[User]:
    res = await session.execute(select(UserModel))
    user_models = res.scalars().all()
    return [user_model_to_user(u) for u in user_models]


async def get_user_with_creds_by_name(
    session: AsyncSession,
    current_user: UserModel,
    username: str,
) -> Optional[User]:
    res = await session.execute(select(UserModel).where(UserModel.name == username))
    user_model = res.scalar()
    if user_model is None:
        return None
    if current_user.global_role == GlobalRole.ADMIN or current_user.id == user_model.id:
        return user_model_to_user_with_creds(user_model)
    return None


async def get_user_model_by_token(session: AsyncSession, token: str) -> Optional[UserModel]:
    res = await session.execute(select(UserModel).where(UserModel.token == token))
    return res.scalar()


def user_model_to_user(user_model: UserModel) -> User:
    return User(
        id=user_model.id,
        username=user_model.name,
        global_role=user_model.global_role,
    )


def user_model_to_user_with_creds(user_model: UserModel) -> UserWithCreds:
    return UserWithCreds(
        id=user_model.id,
        username=user_model.name,
        global_role=user_model.global_role,
        creds=UserTokenCreds(token=user_model.token),
    )
