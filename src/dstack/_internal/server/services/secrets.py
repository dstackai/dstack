import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Dict, List, Optional

import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.secrets import Secret
from dstack._internal.server.db import get_db
from dstack._internal.server.models import DecryptedString, ProjectModel, SecretModel, UserModel
from dstack._internal.server.services import events
from dstack._internal.server.services.locking import get_locker

_SECRET_NAME_REGEX = "^[A-Za-z0-9-_]{1,200}$"
_SECRET_VALUE_MAX_LENGTH = 5000


async def list_secrets(
    session: AsyncSession,
    project: ProjectModel,
) -> List[Secret]:
    secret_models = await list_project_secret_models(session=session, project=project)
    return [secret_model_to_secret(s, include_value=False) for s in secret_models]


async def get_project_secrets_mapping(
    session: AsyncSession,
    project: ProjectModel,
) -> Dict[str, str]:
    secret_models = await list_project_secret_models(session=session, project=project)
    return {s.name: s.value.get_plaintext_or_error() for s in secret_models}


async def get_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
) -> Optional[Secret]:
    secret_model = await get_project_secret_model_by_name(
        session=session,
        project=project,
        name=name,
    )
    if secret_model is None:
        return None
    return secret_model_to_secret(secret_model, include_value=True)


async def create_or_update_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    value: str,
    user: UserModel,
) -> Secret:
    _validate_secret(name=name, value=value)
    try:
        secret_model = await create_secret(
            session=session,
            project=project,
            name=name,
            value=value,
            user=user,
        )
    except ResourceExistsError:
        secret_model = await update_secret(
            session=session,
            project=project,
            name=name,
            value=value,
            user=user,
        )
    return secret_model_to_secret(secret_model, include_value=True)


async def delete_secrets(
    session: AsyncSession,
    project: ProjectModel,
    names: List[str],
    user: UserModel,
):
    async with get_project_secret_models_by_name_for_update(
        session=session, project=project, names=names
    ) as secret_models:
        existing_names = [s.name for s in secret_models]
        missing_names = set(names) - set(existing_names)
        if missing_names:
            raise ResourceNotExistsError(f"Secrets not found: {', '.join(missing_names)}")
        for secret_model in secret_models:
            await session.delete(secret_model)
            events.emit(
                session,
                "Secret deleted",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(secret_model)],
            )
        await session.commit()


def secret_model_to_secret(secret_model: SecretModel, include_value: bool = False) -> Secret:
    value = None
    if include_value:
        value = secret_model.value.get_plaintext_or_error()
    return Secret(
        id=secret_model.id,
        name=secret_model.name,
        value=value,
    )


async def list_project_secret_models(
    session: AsyncSession,
    project: ProjectModel,
) -> List[SecretModel]:
    res = await session.execute(
        select(SecretModel)
        .where(
            SecretModel.project_id == project.id,
        )
        .order_by(SecretModel.created_at.desc())
    )
    secret_models = list(res.scalars().all())
    return secret_models


async def get_project_secret_model_by_name(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
) -> Optional[SecretModel]:
    res = await session.execute(
        select(SecretModel).where(
            SecretModel.project_id == project.id,
            SecretModel.name == name,
        )
    )
    return res.scalar_one_or_none()


@asynccontextmanager
async def get_project_secret_models_by_name_for_update(
    session: AsyncSession, project: ProjectModel, names: list[str]
) -> AsyncGenerator[list[SecretModel], None]:
    """
    Fetch secrets from the database and lock them for update.

    **NOTE**: commit changes to the database before exiting from this context manager,
              so that in-memory locks are only released after commit.
    """
    filters = [
        SecretModel.project_id == project.id,
        SecretModel.name.in_(names),
    ]
    res = await session.execute(select(SecretModel.id).where(*filters))
    secret_ids = res.scalars().all()
    if not secret_ids:
        yield []
    else:
        async with get_locker(get_db().dialect_name).lock_ctx(
            SecretModel.__tablename__, sorted(secret_ids)
        ):
            # Refetch after lock
            res = await session.execute(
                select(SecretModel)
                .where(SecretModel.id.in_(secret_ids), *filters)
                .with_for_update(key_share=True)
                .order_by(SecretModel.id)  # take locks in order
            )
            yield list(res.scalars().all())


async def create_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    value: str,
    user: UserModel,
) -> SecretModel:
    secret_model = SecretModel(
        id=uuid.uuid4(),
        project_id=project.id,
        name=name,
        value=DecryptedString(plaintext=value),
    )
    try:
        async with session.begin_nested():
            session.add(secret_model)
            events.emit(
                session,
                "Secret created",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(secret_model)],
            )
    except sqlalchemy.exc.IntegrityError:
        raise ResourceExistsError()
    await session.commit()
    return secret_model


async def update_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    value: str,
    user: UserModel,
) -> SecretModel:
    async with get_project_secret_models_by_name_for_update(
        session=session, project=project, names=[name]
    ) as secret_models:
        if not secret_models:
            raise ResourceNotExistsError()
        secret_model = secret_models[0]
        if secret_model.value.get_plaintext_or_error() != value:
            secret_model.value = DecryptedString(plaintext=value)
            events.emit(
                session,
                "Secret updated",
                actor=events.UserActor.from_user(user),
                targets=[events.Target.from_model(secret_model)],
            )
            await session.commit()
    return secret_model


def _validate_secret(name: str, value: str):
    _validate_secret_name(name)
    _validate_secret_value(value)


def _validate_secret_name(name: str):
    if re.match(_SECRET_NAME_REGEX, name) is None:
        raise ServerClientError(f"Secret name should match regex '{_SECRET_NAME_REGEX}")


def _validate_secret_value(value: str):
    if len(value) > _SECRET_VALUE_MAX_LENGTH:
        raise ServerClientError(f"Secret value length must not exceed {_SECRET_VALUE_MAX_LENGTH}")
