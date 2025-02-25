import re

from dstack._internal.core.errors import ServerClientError


def validate_dstack_resource_name(resource_name: str):
    if not is_valid_dstack_resource_name(resource_name):
        raise ServerClientError("Resource name should match regex '^[a-z][a-z0-9-]{1,40}$'")


def is_valid_dstack_resource_name(resource_name: str) -> bool:
    return re.match("^[a-z][a-z0-9-]{1,40}$", resource_name) is not None
