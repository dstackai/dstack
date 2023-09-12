from typing import List

from pydantic import BaseModel

from dstack._internal.core.models.backends import BackendType


class DeleteBackendsRequest(BaseModel):
    backends_names: List[BackendType]
