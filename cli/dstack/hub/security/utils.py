from typing import Union

from typing_extensions import Literal

ROLE_ADMIN = "admin"
ROLE_RUN = "run"
ROLE_READ = "read"

GlobalRole = Union[Literal["admin"], Literal["read"]]
ProjectRole = Union[Literal["admin"], Literal["run"], Literal["read"]]
