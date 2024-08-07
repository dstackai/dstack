import re

from dstack._internal.core.errors import ServerClientError


def validate_dstack_resource_name(resource_name: str):
    if not re.match("^[a-z][a-z0-9-]{1,40}$", resource_name):
        raise ServerClientError("Resource name should match regex '^[a-z][a-z0-9-]{1,40}$'")
