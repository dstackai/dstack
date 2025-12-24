import hashlib
import os
import re
import secrets
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Awaitable, Callable, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy import func as safunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from dstack._internal.core.errors import (
    ResourceExistsError,
    ServerClientError,
)
from dstack._internal.core.models.users import (
    GlobalRole,
    User,
    UserHookConfig,
    UserPermissions,
    UserTokenCreds,
    UserWithCreds,
)
from dstack._internal.server.db import get_db
from dstack._internal.server.models import DecryptedString, MemberModel, UserModel
from dstack._internal.server.services import events
from dstack._internal.server.services.locking import get_locker
from dstack._internal.server.services.permissions import get_default_permissions
from dstack._internal.server.utils.routers import error_forbidden
from dstack._internal.utils import crypto
from dstack._internal.utils.common import get_current_datetime, get_or_error, run_async
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
    include_deleted: bool = False,
) -> List[User]:
    filters = []
    if not include_deleted:
        filters.append(UserModel.deleted == False)
    res = await session.execute(select(UserModel).where(*filters))
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
    config: Optional[UserHookConfig] = None,
    creator: Optional[UserModel] = None,
) -> UserModel:
    validate_username(username)
    user_model = await get_user_model_by_name(session=session, username=username, ignore_case=True)
    if user_model is not None:
        raise ResourceExistsError()
    if token is None:
        token = str(uuid.uuid4())
    private_bytes, public_bytes = await run_async(crypto.generate_rsa_key_pair_bytes, username)
    user = UserModel(
        id=uuid.uuid4(),
        name=username,
        global_role=global_role,
        token=DecryptedString(plaintext=token),
        token_hash=get_token_hash(token),
        email=email,
        active=active,
        ssh_private_key=private_bytes.decode(),
        ssh_public_key=public_bytes.decode(),
    )
    session.add(user)
    events.emit(
        session,
        "User created",
        actor=events.UserActor.from_user(creator) if creator else events.UserActor.from_user(user),
        targets=[events.Target.from_model(user)],
    )
    await session.commit()
    for func in _CREATE_USER_HOOKS:
        await func(session, user, config)
    return user


async def update_user(
    session: AsyncSession,
    actor: events.AnyActor,
    username: str,
    global_role: GlobalRole,
    email: Optional[str] = None,
    active: bool = True,
) -> Optional[UserModel]:
    async with get_user_model_by_name_for_update(session, username) as user:
        if user is None:
            return None
        updated_fields = []
        if global_role != user.global_role:
            user.global_role = global_role
            updated_fields.append(f"global_role={global_role}")
        if email != user.email:
            user.email = email
            updated_fields.append("email")  # do not include potentially sensitive new value
        if active != user.active:
            user.active = active
            updated_fields.append(f"active={active}")
        events.emit(
            session,
            f"User updated. Updated fields: {', '.join(updated_fields) or '<none>'}",
            actor=actor,
            targets=[events.Target.from_model(user)],
        )
        await session.commit()
    return user


async def refresh_ssh_key(
    session: AsyncSession,
    actor: UserModel,
    username: Optional[str] = None,
) -> Optional[UserModel]:
    if username is None:
        username = actor.name
    if actor.global_role != GlobalRole.ADMIN and actor.name != username:
        raise error_forbidden()
    async with get_user_model_by_name_for_update(session, username) as user:
        if user is None:
            return None
        private_bytes, public_bytes = await run_async(crypto.generate_rsa_key_pair_bytes, username)
        user.ssh_private_key = private_bytes.decode()
        user.ssh_public_key = public_bytes.decode()
        events.emit(
            session,
            "User SSH key refreshed",
            actor=events.UserActor.from_user(actor),
            targets=[events.Target.from_model(user)],
        )
        await session.commit()
    return user


async def refresh_user_token(
    session: AsyncSession,
    actor: UserModel,
    username: str,
) -> Optional[UserModel]:
    if actor.global_role != GlobalRole.ADMIN and actor.name != username:
        raise error_forbidden()
    async with get_user_model_by_name_for_update(session, username) as user:
        if user is None:
            return None
        new_token = str(uuid.uuid4())
        user.token = DecryptedString(plaintext=new_token)
        user.token_hash = get_token_hash(new_token)
        events.emit(
            session,
            "User token refreshed",
            actor=events.UserActor.from_user(actor),
            targets=[events.Target.from_model(user)],
        )
        await session.commit()
    return user


async def delete_users(
    session: AsyncSession,
    actor: UserModel,
    usernames: List[str],
):
    if _ADMIN_USERNAME in usernames:
        raise ServerClientError(f"User {_ADMIN_USERNAME!r} cannot be deleted")

    filters = [
        UserModel.name.in_(usernames),
        UserModel.deleted == False,
    ]
    res = await session.execute(select(UserModel.id).where(*filters))
    user_ids = list(res.scalars().all())
    user_ids.sort()

    async with get_locker(get_db().dialect_name).lock_ctx(UserModel.__tablename__, user_ids):
        # Refetch after lock
        res = await session.execute(
            select(UserModel)
            .where(UserModel.id.in_(user_ids), *filters)
            .order_by(UserModel.id)  # take locks in order
            .options(load_only(UserModel.id, UserModel.name))
            .with_for_update(key_share=True)
        )
        users = list(res.scalars().all())
        if len(users) != len(usernames):
            raise ServerClientError("Failed to delete non-existent users")
        user_ids = [u.id for u in users]
        timestamp = str(int(get_current_datetime().timestamp()))
        for u in users:
            event_target = events.Target.from_model(u)  # build target before renaming the user
            u.deleted = True
            u.active = False
            u.original_name = u.name
            u.name = f"_deleted_{timestamp}_{secrets.token_hex(8)}"
            events.emit(
                session,
                "User deleted",
                actor=events.UserActor.from_user(actor),
                targets=[event_target],
            )
        await session.execute(delete(MemberModel).where(MemberModel.user_id.in_(user_ids)))
        # Projects are not deleted automatically if owners are deleted.
        await session.commit()


async def get_user_model_by_name(
    session: AsyncSession,
    username: str,
    ignore_case: bool = False,
) -> Optional[UserModel]:
    filters = [UserModel.deleted == False]
    if ignore_case:
        filters.append(safunc.lower(UserModel.name) == safunc.lower(username))
    else:
        filters.append(UserModel.name == username)
    res = await session.execute(select(UserModel).where(*filters))
    return res.scalar()


async def get_user_model_by_name_or_error(
    session: AsyncSession,
    username: str,
    ignore_case: bool = False,
) -> UserModel:
    return get_or_error(
        await get_user_model_by_name(session=session, username=username, ignore_case=ignore_case)
    )


@asynccontextmanager
async def get_user_model_by_name_for_update(
    session: AsyncSession, username: str
) -> AsyncGenerator[Optional[UserModel], None]:
    """
    Fetch the user from the database and lock it for update.

    **NOTE**: commit changes to the database before exiting from this context manager,
              so that in-memory locks are only released after commit.
    """

    filters = [
        UserModel.name == username,
        UserModel.deleted == False,
    ]
    res = await session.execute(select(UserModel.id).where(*filters))
    user_id = res.scalar_one_or_none()
    if user_id is None:
        yield None
    else:
        async with get_locker(get_db().dialect_name).lock_ctx(UserModel.__tablename__, [user_id]):
            # Refetch after lock
            res = await session.execute(
                select(UserModel)
                .where(UserModel.id.in_([user_id]), *filters)
                .with_for_update(key_share=True)
            )
            yield res.scalar_one_or_none()


async def log_in_with_token(session: AsyncSession, token: str) -> Optional[UserModel]:
    token_hash = get_token_hash(token)
    res = await session.execute(
        select(UserModel).where(
            UserModel.token_hash == token_hash,
            UserModel.active == True,
            UserModel.deleted == False,
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
        ssh_public_key=user_model.ssh_public_key,
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
        ssh_public_key=user_model.ssh_public_key,
        creds=UserTokenCreds(token=user_model.token.get_plaintext_or_error()),
        ssh_private_key=user_model.ssh_private_key,
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


def register_create_user_hook(
    func: Callable[[AsyncSession, UserModel, Optional[UserHookConfig]], Awaitable[None]],
):
    _CREATE_USER_HOOKS.append(func)


def get_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
