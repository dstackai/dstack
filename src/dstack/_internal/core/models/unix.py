from typing import Optional

from pydantic import Field
from typing_extensions import Annotated, Self

from dstack._internal.core.models.common import CoreModel


class UnixUser(CoreModel):
    uid: Annotated[Optional[int], Field(description="User ID", ge=0)] = None
    gid: Annotated[Optional[int], Field(description="Group ID", ge=0)] = None
    username: Annotated[Optional[str], Field(description="User name", min_length=1)] = None
    groupname: Annotated[Optional[str], Field(description="Group name", min_length=1)] = None

    @classmethod
    def parse(cls, v: str) -> Self:
        """
        Parse `<user>[:<group>]` format used by Docker.
        """
        try:
            return cls._parse(v)
        except ValueError as e:
            raise ValueError(f"invalid user format: {e}")

    @classmethod
    def _parse(cls, v: str) -> Self:
        parts = v.split(":")
        if len(parts) > 2:
            raise ValueError("too many parts")
        uid: Optional[int] = None
        gid: Optional[int] = None
        username: Optional[str] = None
        groupname: Optional[str] = None
        user_name_or_id = parts[0]
        if not user_name_or_id:
            raise ValueError("empty user name or id")
        try:
            uid = int(user_name_or_id)
        except ValueError:
            username = user_name_or_id
        if uid is not None and uid < 0:
            raise ValueError(f"negative uid {uid}")
        if len(parts) == 2:
            group_name_or_id = parts[1]
            if not group_name_or_id:
                raise ValueError("empty group name or id")
            try:
                gid = int(group_name_or_id)
            except ValueError:
                groupname = group_name_or_id
            if gid is not None and gid < 0:
                raise ValueError(f"negative gid {gid}")
        return cls(uid=uid, gid=gid, username=username, groupname=groupname)
