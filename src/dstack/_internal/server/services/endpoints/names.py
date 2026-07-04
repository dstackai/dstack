from typing import Optional

_DSTACK_RESOURCE_NAME_MAX_LENGTH = 41
_SERVING_RUN_SUFFIX = "-serving"


def get_endpoint_serving_run_name(endpoint_name: Optional[str]) -> Optional[str]:
    if endpoint_name is None:
        return None
    if len(endpoint_name) + len(_SERVING_RUN_SUFFIX) <= _DSTACK_RESOURCE_NAME_MAX_LENGTH:
        return f"{endpoint_name}{_SERVING_RUN_SUFFIX}"
    return endpoint_name
