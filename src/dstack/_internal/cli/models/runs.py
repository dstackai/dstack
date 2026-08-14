from typing import List

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.runs import Run


class PsCommandOutput(CoreModel):
    """JSON output model for `dstack ps` command."""

    project: str
    runs: List[Run]
