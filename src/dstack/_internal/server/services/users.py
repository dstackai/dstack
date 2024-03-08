import uuid
from typing import Awaitable, Callable, List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy import func as safunc
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceExistsError
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


async def list_users_for_user(
    session: AsyncSession,
    user: UserModel,
) -> List[User]:
    if user.global_role == GlobalRole.ADMIN:
        return await list_all_users(session=session)
    return [user_model_to_user(user)]


async def list_all_users(
    session: AsyncSession,
) -> List[User]:
    res = await session.execute(select(UserModel))
    user_models = res.scalars().all()
    return [user_model_to_user(u) for u in user_models]


async def get_user_with_creds_by_name(
    session: AsyncSession,
    current_user: UserModel,
    username: str,
) -> Optional[UserWithCreds]:
    user_model = await get_user_model_by_name(session=session, username=username)
    if user_model is None:
        return None
    if current_user.global_role == GlobalRole.ADMIN or current_user.id == user_model.id:
        return user_model_to_user_with_creds(user_model)
    return None


async def create_user(
    session: AsyncSession,
    username: str,
    global_role: GlobalRole,
    email: Optional[str] = None,
) -> UserModel:
    user_model = await get_user_model_by_name(session=session, username=username, ignore_case=True)
    if user_model is not None:
        raise ResourceExistsError()
    user = UserModel(
        id=uuid.uuid4(),
        name=username,
        global_role=global_role,
        token=str(uuid.uuid4()),
        email=email,
    )
    session.add(user)
    await session.commit()
    for func in _CREATE_USER_HOOKS:
        await func(session, user)
    return user


async def update_user(
    session: AsyncSession,
    username: str,
    global_role: GlobalRole,
    email: Optional[str] = None,
) -> UserModel:
    await session.execute(
        update(UserModel)
        .where(UserModel.name == username)
        .values(global_role=global_role, email=email)
    )
    await session.commit()
    return await get_user_model_by_name_or_error(session=session, username=username)


async def refresh_user_token(session: AsyncSession, username: str) -> Optional[UserModel]:
    await session.execute(
        update(UserModel).where(UserModel.name == username).values(token=uuid.uuid4())
    )
    await session.commit()
    return await get_user_model_by_name(session=session, username=username)


async def delete_users(
    session: AsyncSession,
    user: UserModel,
    usernames: List[str],
):
    await session.execute(delete(UserModel).where(UserModel.name.in_(usernames)))
    await session.commit()


async def get_user_model_by_name(
    session: AsyncSession,
    username: str,
    ignore_case: bool = False,
) -> Optional[UserModel]:
    filters = []
    if ignore_case:
        filters.append(safunc.lower(UserModel.name) == safunc.lower(username))
    else:
        filters.append(UserModel.name == username)
    res = await session.execute(select(UserModel).where(*filters))
    return res.scalar()


async def get_user_model_by_name_or_error(session: AsyncSession, username: str) -> UserModel:
    res = await session.execute(select(UserModel).where(UserModel.name == username))
    return res.scalar_one()


async def get_user_model_by_token(session: AsyncSession, token: str) -> Optional[UserModel]:
    res = await session.execute(select(UserModel).where(UserModel.token == token))
    return res.scalar()


def user_model_to_user(user_model: UserModel) -> User:
    return User(
        id=user_model.id,
        username=user_model.name,
        global_role=user_model.global_role,
        email=user_model.email,
    )


def user_model_to_user_with_creds(user_model: UserModel) -> UserWithCreds:
    return UserWithCreds(
        id=user_model.id,
        username=user_model.name,
        global_role=user_model.global_role,
        email=user_model.email,
        creds=UserTokenCreds(token=user_model.token),
    )


_CREATE_USER_HOOKS = []


def register_create_user_hook(func: Callable[[AsyncSession, UserModel], Awaitable[None]]):
    _CREATE_USER_HOOKS.append(func)
