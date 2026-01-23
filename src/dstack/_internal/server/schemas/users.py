from datetime import datetime
from typing import Annotated, List, Optional
from uuid import UUID

from pydantic import Field

from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.users import GlobalRole


class ListUsersRequest(CoreModel):
    return_total_count: Annotated[
        bool, Field(description="Return `total_count` with the total number of users.")
    ] = False
    name_pattern: Annotated[
        Optional[str],
        Field(
            description="Include only users with the name containing `name_pattern`.",
            regex="^[a-zA-Z0-9-_]*$",
        ),
    ] = None
    prev_created_at: Annotated[
        Optional[datetime],
        Field(
            description=(
                "Paginate users by specifying `created_at` of the last (first) user in previous "
                "batch for descending (ascending)."
            )
        ),
    ] = None
    prev_id: Annotated[
        Optional[UUID],
        Field(
            description=(
                "Paginate users by specifying `id` of the last (first) user in previous batch "
                "for descending (ascending). Must be used together with `prev_created_at`."
            )
        ),
    ] = None
    limit: Annotated[int, Field(ge=0, le=2000, description="Limit number of users returned.")] = (
        2000
    )
    ascending: Annotated[
        bool,
        Field(
            description=(
                "Return users sorted by `created_at` in ascending order. Defaults to descending."
            )
        ),
    ] = False


class GetUserRequest(CoreModel):
    username: str


class CreateUserRequest(CoreModel):
    username: str
    global_role: GlobalRole
    email: Optional[str]
    active: bool = True


UpdateUserRequest = CreateUserRequest


class RefreshTokenRequest(CoreModel):
    username: str


class DeleteUsersRequest(CoreModel):
    users: List[str]
