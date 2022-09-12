from typing import Optional, List, Dict

from fastapi import APIRouter
from pydantic import BaseModel

from dstack.backend import load_backend

DEFAULT_SINCE_DAYS = 1

router = APIRouter(prefix="/api/logs", tags=["logs"])


class AppSpecItem(BaseModel):
    port_index: int
    app_name: str
    url_path: Optional[str]
    url_query_params: Optional[Dict[str, str]]


class LogEventItem(BaseModel):
    event_id: str
    timestamp: int
    message: str
    source: str


class LogsCacheItem(BaseModel):
    job_host_names: Dict[str, Optional[str]]
    job_ports: Dict[str, Optional[List[int]]]
    job_app_specs: Dict[str, Optional[List[AppSpecItem]]]


class QueryLogsRequest(BaseModel):
    repo_user_name: str
    repo_name: str
    run_name: str
    start_time: int
    end_time: Optional[int]
    next_token: Optional[str]
    cache: Optional[LogsCacheItem]


class QueryLogsResponse(BaseModel):
    events: List[LogEventItem]
    next_token: Optional[str]
    cache: Optional[LogsCacheItem]


@router.post("/query", response_model=QueryLogsResponse)
async def query(request: QueryLogsRequest) -> QueryLogsResponse:
    backend = load_backend()
    logs_response = backend.query_logs(request.repo_user_name, request.repo_name, request.run_name, request.start_time,
                                       request.end_time, request.next_token,
                                       (request.cache.job_host_names or {}) if request.cache else {},
                                       (request.cache.job_ports or {}) if request.cache else {},
                                       (request.cache.job_app_specs or {}) if request.cache else {})
    events, next_token, job_host_names, job_ports, job_app_specs = logs_response
    return QueryLogsResponse(
        events=[
            LogEventItem(
                event_id=e.event_id,
                timestamp=e.timestamp,
                message=e.log_message,
                source=e.log_source.value
            ) for e in events
        ],
        next_token=next_token,
        cache=LogsCacheItem(
            job_host_names=job_host_names,
            job_ports=job_ports,
            job_app_specs=job_app_specs
        )
    )
