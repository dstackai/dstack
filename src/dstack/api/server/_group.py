from logging import Logger
from typing import Optional, Union

import requests
from typing_extensions import Protocol


class APIRequest(Protocol):
    def __call__(
        self,
        path: str,
        body: Optional[Union[str, bytes]] = None,
        raise_for_status: bool = True,
        method: str = "POST",
        **kwargs,
    ) -> requests.Response: ...


class APIClientGroup:
    def __init__(self, _request: APIRequest, _logger: Logger):
        self._request = _request
        self._logger = _logger
