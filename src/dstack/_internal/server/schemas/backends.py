from typing import List

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import CoreModel


class DeleteBackendsRequest(CoreModel):
    backends_names: List[BackendType]
