from typing import Optional, Union

import requests
from typing_extensions import Protocol


class APIRequest(Protocol):
    def __call__(
        self, path: str, body: Optional[str] = None, raise_for_status: bool = True, **kwargs
    ) -> requests.Response:
        ...


class APIClientGroup:
    def __init__(self, _request: APIRequest):
        self._request = _request
