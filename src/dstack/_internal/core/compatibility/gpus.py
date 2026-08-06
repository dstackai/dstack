from typing import Optional

from dstack._internal.core.compatibility.runs import get_run_spec_excludes
from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.gpus import ListGpusRequest


def get_list_gpus_excludes(request: ListGpusRequest) -> Optional[IncludeExcludeDictType]:
    list_gpus_excludes: IncludeExcludeDictType = {}
    run_spec_excludes = get_run_spec_excludes(request.run_spec)
    if run_spec_excludes is not None:
        list_gpus_excludes["run_spec"] = run_spec_excludes
    return list_gpus_excludes
