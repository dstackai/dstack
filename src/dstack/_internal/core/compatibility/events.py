from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.events import ListEventsRequest


def get_list_events_excludes(request: ListEventsRequest) -> IncludeExcludeDictType:
    list_events_excludes: IncludeExcludeDictType = {}
    if request.target_presets is None:
        list_events_excludes["target_presets"] = True
    return list_events_excludes
