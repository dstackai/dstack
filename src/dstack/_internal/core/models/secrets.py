from typing import Optional
from uuid import UUID

from dstack._internal.core.models.common import CoreModel


class Secret(CoreModel):
    id: UUID
    name: str
    value: Optional[str] = None

    def __str__(self) -> str:
        displayed_value = "*"
        if self.value is not None:
            displayed_value = "*" * len(self.value)
        return f'Secret(name="{self.name}", value={displayed_value})'
