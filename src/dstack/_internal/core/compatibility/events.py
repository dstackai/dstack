from dstack._internal.core.models.common import IncludeExcludeDictType
from dstack._internal.server.schemas.events import ListEventsRequest


def get_list_events_excludes(request: ListEventsRequest) -> IncludeExcludeDictType:
    list_gpus_excludes: IncludeExcludeDictType = {}
    return list_gpus_excludes
