import re
from typing import Dict, List, Optional

import sqlalchemy.exc
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import (
    ResourceExistsError,
    ResourceNotExistsError,
    ServerClientError,
)
from dstack._internal.core.models.secrets import Secret
from dstack._internal.server.models import DecryptedString, ProjectModel, SecretModel
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


_SECRET_NAME_REGEX = "^[A-Za-z0-9-_]{1,200}$"
_SECRET_VALUE_MAX_LENGTH = 3000


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
) -> Secret:
    _validate_secret(name=name, value=value)
    try:
        secret_model = await create_secret(
            session=session,
            project=project,
            name=name,
            value=value,
        )
    except ResourceExistsError:
        secret_model = await update_secret(
            session=session,
            project=project,
            name=name,
            value=value,
        )
    return secret_model_to_secret(secret_model, include_value=True)


async def delete_secrets(
    session: AsyncSession,
    project: ProjectModel,
    names: List[str],
):
    existing_secrets_query = await session.execute(
        select(SecretModel).where(
            SecretModel.project_id == project.id,
            SecretModel.name.in_(names),
        )
    )
    existing_names = [s.name for s in existing_secrets_query.scalars().all()]
    missing_names = set(names) - set(existing_names)
    if missing_names:
        raise ResourceNotExistsError(f"Secrets not found: {', '.join(missing_names)}")

    await session.execute(
        delete(SecretModel).where(
            SecretModel.project_id == project.id,
            SecretModel.name.in_(names),
        )
    )
    await session.commit()
    logger.info("Deleted secrets %s in project %s", names, project.name)


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


async def create_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    value: str,
) -> SecretModel:
    secret_model = SecretModel(
        project_id=project.id,
        name=name,
        value=DecryptedString(plaintext=value),
    )
    try:
        async with session.begin_nested():
            session.add(secret_model)
    except sqlalchemy.exc.IntegrityError:
        raise ResourceExistsError()
    await session.commit()
    return secret_model


async def update_secret(
    session: AsyncSession,
    project: ProjectModel,
    name: str,
    value: str,
) -> SecretModel:
    await session.execute(
        update(SecretModel)
        .where(
            SecretModel.project_id == project.id,
            SecretModel.name == name,
        )
        .values(
            value=DecryptedString(plaintext=value),
        )
    )
    await session.commit()
    secret_model = await get_project_secret_model_by_name(
        session=session,
        project=project,
        name=name,
    )
    if secret_model is None:
        raise ResourceNotExistsError()
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
