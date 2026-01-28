from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.events import ListEventsRequest


def get_list_events_excludes(request: ListEventsRequest) -> IncludeExcludeDictType:
    list_gpus_excludes: IncludeExcludeDictType = {}
    if request.target_volumes is None:
        list_gpus_excludes["target_volumes"] = True
    if request.target_gateways is None:
        list_gpus_excludes["target_gateways"] = True
    if request.target_secrets is None:
        list_gpus_excludes["target_secrets"] = True
    return list_gpus_excludes
