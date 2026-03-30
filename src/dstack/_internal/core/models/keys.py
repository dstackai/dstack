import datetime
import uuid

from dstack._internal.core.models.common import CoreModel


class PublicKeyInfo(CoreModel):
    id: uuid.UUID
    added_at: datetime.datetime
    name: str
    type: str
    fingerprint: str
