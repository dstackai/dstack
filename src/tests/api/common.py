import json
from dataclasses import dataclass, field
from typing import Any, Optional

import requests


@dataclass
class RequestRecorder:
    payload: Any
    last_path: Optional[str] = None
    last_body: Optional[str] = None
    last_kwargs: dict[str, Any] = field(default_factory=dict)

    def __call__(
        self,
        path: str,
        body: Optional[str] = None,
        raise_for_status: bool = True,
        method: str = "POST",
        **kwargs,
    ) -> requests.Response:
        self.last_path = path
        self.last_body = body
        self.last_kwargs = kwargs
        resp = requests.Response()
        resp.status_code = 200
        resp._content = json.dumps(self.payload).encode("utf-8")
        return resp
