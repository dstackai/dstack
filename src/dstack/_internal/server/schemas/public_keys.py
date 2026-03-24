import uuid
from typing import Optional

from dstack._internal.core.models.common import CoreModel


class AddPublicKeyRequest(CoreModel):
    key: str
    name: Optional[str] = None


class DeletePublicKeysRequest(CoreModel):
    ids: list[uuid.UUID]
