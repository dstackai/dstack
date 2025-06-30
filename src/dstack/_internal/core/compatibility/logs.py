from typing import Dict, Optional

from dstack._internal.server.schemas.logs import PollLogsRequest


def get_poll_logs_excludes(request: PollLogsRequest) -> Optional[Dict]:
    """
    Returns exclude mapping to exclude certain fields from the request.
    Use this method to exclude new fields when they are not set to keep
    clients backward-compatibility with older servers.
    """
    excludes = {}
    if request.next_token is None:
        excludes["next_token"] = True
    return excludes if excludes else None
