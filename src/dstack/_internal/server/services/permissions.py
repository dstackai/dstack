from pydantic import Field
from typing_extensions import Annotated

from dstack._internal.core.models.common import CoreModel


class DefaultPermissions(CoreModel):
    allow_non_admins_create_projects: Annotated[
        bool,
        Field(
            description=(
                "This flag controls whether regular users (non-global admins)"
                " can create and manage their own projects"
            )
        ),
    ] = True
    allow_non_admins_manage_ssh_fleets: Annotated[
        bool,
        Field(
            description=(
                "This flag controls whether regular project members (i.e. Users)"
                " can add and delete SSH fleets"
            )
        ),
    ] = True


_default_permissions = DefaultPermissions()


def set_default_permissions(default_permissions: DefaultPermissions):
    global _default_permissions
    _default_permissions = default_permissions


def get_default_permissions() -> DefaultPermissions:
    return _default_permissions
