import hashlib
import os
import re
import uuid
from typing import Awaitable, Callable, List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy import func as safunc
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceExistsError, ServerClientError
from dstack._internal.core.models.users import (
    GlobalRole,
    User,
    UserPermissions,
    UserTokenCreds,
    UserWithCreds,
)
from dstack._internal.server.models import DecryptedString, UserModel
from dstack._internal.server.services.permissions import get_default_permissions
from dstack._internal.server.utils.routers import error_forbidden
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

_ADMIN_USERNAME = "admin"


async def get_or_create_admin_user(session: AsyncSession) -> Tuple[UserModel, bool]:
    admin = await get_user_model_by_name(session=session, username=_ADMIN_USERNAME)
    if admin is not None:
        return admin, False
    admin = await create_user(
        session=session,
        username=_ADMIN_USERNAME,
        global_role=GlobalRole.ADMIN,
        token=os.getenv("DSTACK_SERVER_ADMIN_TOKEN"),
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
    user_models = sorted(user_models, key=lambda u: u.created_at)
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
    active: bool = True,
    token: Optional[str] = None,
) -> UserModel:
    validate_username(username)
    user_model = await get_user_model_by_name(session=session, username=username, ignore_case=True)
    if user_model is not None:
        raise ResourceExistsError()
    if token is None:
        token = str(uuid.uuid4())
    user = UserModel(
        id=uuid.uuid4(),
        name=username,
        global_role=global_role,
        token=DecryptedString(plaintext=token),
        token_hash=get_token_hash(token),
        email=email,
        active=active,
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
    active: bool = True,
) -> UserModel:
    await session.execute(
        update(UserModel)
        .where(UserModel.name == username)
        .values(
            global_role=global_role,
            email=email,
            active=active,
        )
    )
    await session.commit()
    return await get_user_model_by_name_or_error(session=session, username=username)


async def refresh_user_token(
    session: AsyncSession,
    user: UserModel,
    username: str,
) -> Optional[UserModel]:
    if user.global_role != GlobalRole.ADMIN and user.name != username:
        raise error_forbidden()
    new_token = str(uuid.uuid4())
    await session.execute(
        update(UserModel)
        .where(UserModel.name == username)
        .values(
            token=DecryptedString(plaintext=new_token),
            token_hash=get_token_hash(new_token),
        )
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
    logger.info("Deleted users %s by user %s", usernames, user.name)


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


async def log_in_with_token(session: AsyncSession, token: str) -> Optional[UserModel]:
    token_hash = get_token_hash(token)
    res = await session.execute(
        select(UserModel).where(
            UserModel.token_hash == token_hash,
            UserModel.active == True,
        )
    )
    user = res.scalar()
    if user is None:
        return None
    if not user.token.decrypted:
        logger.error(
            "Failed to get user by token. Token cannot be decrypted: %s", repr(user.token.exc)
        )
        return None
    if user.token.get_plaintext_or_error() != token:
        return None
    return user


def user_model_to_user(user_model: UserModel) -> User:
    return User(
        id=user_model.id,
        username=user_model.name,
        created_at=user_model.created_at,
        global_role=user_model.global_role,
        email=user_model.email,
        active=user_model.active,
        permissions=get_user_permissions(user_model),
    )


def user_model_to_user_with_creds(user_model: UserModel) -> UserWithCreds:
    return UserWithCreds(
        id=user_model.id,
        username=user_model.name,
        created_at=user_model.created_at,
        global_role=user_model.global_role,
        email=user_model.email,
        active=user_model.active,
        permissions=get_user_permissions(user_model),
        creds=UserTokenCreds(token=user_model.token.get_plaintext_or_error()),
    )


def get_user_permissions(user_model: UserModel) -> UserPermissions:
    default_permissions = get_default_permissions()
    can_create_projects = True
    if not default_permissions.allow_non_admins_create_projects:
        if user_model.global_role != GlobalRole.ADMIN:
            can_create_projects = False
    return UserPermissions(
        can_create_projects=can_create_projects,
    )


def validate_username(username: str):
    if not is_valid_username(username):
        raise ServerClientError("Username should match regex '^[a-zA-Z0-9-_]{1,60}$'")


def is_valid_username(username: str) -> bool:
    return re.match("^[a-zA-Z0-9-_]{1,60}$", username) is not None


_CREATE_USER_HOOKS = []


def register_create_user_hook(func: Callable[[AsyncSession, UserModel], Awaitable[None]]):
    _CREATE_USER_HOOKS.append(func)


def get_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
