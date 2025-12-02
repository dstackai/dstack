from typing import List

from dstack._internal.core.models.common import CoreConfig, generate_dual_core_model
from dstack._internal.core.models.runs import Run
from dstack._internal.utils.json_utils import pydantic_orjson_dumps_with_indent


class PsCommandOutputConfig(CoreConfig):
    json_dumps = pydantic_orjson_dumps_with_indent


class PsCommandOutput(generate_dual_core_model(PsCommandOutputConfig)):
    """JSON output model for `dstack ps` command."""

    project: str
    runs: List[Run]
