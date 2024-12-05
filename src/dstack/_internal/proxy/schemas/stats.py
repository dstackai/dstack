from pydantic import BaseModel


class Stat(BaseModel):
    requests: int
    request_time: float


PerWindowStats = dict[int, Stat]  # keys - length of time window in seconds


class ServiceStats(BaseModel):
    project_name: str
    run_name: str
    stats: PerWindowStats
