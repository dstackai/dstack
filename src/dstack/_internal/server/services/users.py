import uuid
from typing import List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.models.users import GlobalRole, User, UserTokenCreds, UserWithCreds
from dstack._internal.server.models import UserModel

_ADMIN_USERNAME = "admin"


async def get_or_create_admin_user(session: AsyncSession) -> Tuple[UserModel, bool]:
    admin = await get_user_model_by_name(session=session, username=_ADMIN_USERNAME)
    if admin is not None:
        return admin, False
    admin = await create_user(
        session=session, username=_ADMIN_USERNAME, global_role=GlobalRole.ADMIN
    )
    return admin, True


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
    user_model = await get_user_model_by_name(session=session, username=username)
    if user_model is None:
        return None
    if current_user.global_role == GlobalRole.ADMIN or current_user.id == user_model.id:
        return user_model_to_user_with_creds(user_model)
    return None


async def create_user(session: AsyncSession, username: str, global_role: GlobalRole) -> UserModel:
    user = UserModel(name=username, global_role=global_role, token=str(uuid.uuid4()))
    session.add(user)
    await session.commit()
    return user


async def update_user_role(
    session: AsyncSession, username: str, global_role: GlobalRole
) -> Optional[UserModel]:
    await session.execute(
        update(UserModel).where(UserModel.name == username).values(global_role=global_role)
    )
    return get_user_model_by_name(session=session, username=username)


async def refresh_user_token(session: AsyncSession, username: str) -> Optional[UserModel]:
    await session.execute(
        update(UserModel).where(UserModel.name == username).values(token=uuid.uuid4())
    )
    return get_user_model_by_name(session=session, username=username)


async def get_user_model_by_name(session: AsyncSession, username: str) -> Optional[UserModel]:
    res = await session.execute(select(UserModel).where(UserModel.name == username))
    return res.scalar()


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
