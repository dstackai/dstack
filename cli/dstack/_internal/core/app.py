from typing import Dict, Optional

from pydantic import BaseModel


class AppSpec(BaseModel):
    port: int
    map_to_port: Optional[int]
    app_name: str
    url_path: Optional[str]
    url_query_params: Optional[Dict[str, str]]


class AppHead(BaseModel):
    job_id: str
    app_name: str
