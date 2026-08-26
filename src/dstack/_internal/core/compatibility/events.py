from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.events import ListEventsRequest


def get_list_events_excludes(request: ListEventsRequest) -> IncludeExcludeDictType:
    list_events_excludes: IncludeExcludeDictType = {}
    if request.target_presets is None:
        list_events_excludes["target_presets"] = True
    if request.target_gateway_replicas is None:
        list_events_excludes["target_gateway_replicas"] = True
    if request.within_gateways is None:
        list_events_excludes["within_gateways"] = True
    return list_events_excludes
