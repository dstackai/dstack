from typing import Optional, Dict

from dstack.utils.common import _quoted


class AppSpec:
    def __init__(
        self,
        port_index: int,
        app_name: str,
        url_path: Optional[str] = None,
        url_query_params: Optional[Dict[str, str]] = None,
    ):
        self.port_index = port_index
        self.app_name = app_name
        self.url_path = url_path
        self.url_query_params = url_query_params

    def __str__(self) -> str:
        return (
            f"AppSpec(app_name={self.app_name}, port_index={self.port_index}, "
            f"url_path={_quoted(self.url_path)}, url_query_params={self.url_query_params})"
        )


class AppHead:
    def __init__(self, job_id: str, app_name: str):
        self.job_id = job_id
        self.app_name = app_name

    def __str__(self) -> str:
        return f'AppHead(job_id="{self.job_id}", app_name="{self.app_name})'
