from pydantic import parse_obj_as

from dstack._internal.core.models.metrics import JobMetrics
from dstack.api.server._group import APIClientGroup


class MetricsAPIClient(APIClientGroup):
    def get_job_metrics(
        self,
        project_name: str,
        run_name: str,
        replica_num: int = 0,
        job_num: int = 0,
    ) -> JobMetrics:
        resp = self._request(
            f"/api/project/{project_name}/metrics/job/{run_name}",
            method="GET",
            params={
                "replica_num": replica_num,
                "job_num": job_num,
            },
        )
        return parse_obj_as(JobMetrics.__response__, resp.json())
