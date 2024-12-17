from dataclasses import dataclass
from typing import Union
from unittest.mock import AsyncMock, MagicMock

AnyMock = Union[MagicMock, AsyncMock]


@dataclass
class Mocks:
    reload_nginx: AnyMock
    run_certbot: AnyMock
    open_conn: AnyMock
    close_conn: AnyMock
