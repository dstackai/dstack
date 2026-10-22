import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.backends.base.compute import generate_provider_ref
from dstack._internal.core.models.backends.orphans import OwnerType
from dstack._internal.server.models import ProjectModel, ProviderRefModel


def issue_provider_ref(
    session: AsyncSession,
    project: ProjectModel,
    owner_type: OwnerType,
    owner_id: uuid.UUID,
    owner_name: str,
) -> str:
    """
    Generates a `provider_ref` for a new owner record and records it in `ProviderRefModel`.
    The record must be committed in the same transaction as the owner record,
    before any provider call that uses the `provider_ref`.
    """
    provider_ref = generate_provider_ref()
    session.add(
        ProviderRefModel(
            provider_ref=provider_ref,
            project_id=project.id,
            owner_type=owner_type,
            owner_id=owner_id,
            owner_name=owner_name,
        )
    )
    return provider_ref
