from datetime import datetime
from typing import Any, Dict, Optional

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.metrics import JobMetrics
from dstack.api.server._group import APIClientGroup


class MetricsAPIClient(APIClientGroup):
    def get_job_metrics(
        self,
        project_name: str,
        run_name: str,
        replica_num: int = 0,
        job_num: int = 0,
        after: Optional[datetime] = None,
        before: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> JobMetrics:
        """
        Returns job metrics ordered from the latest sample to the earliest.

        Without `after`/`before`/`limit`, the server returns one latest sample.
        """
        params: Dict[str, Any] = {
            "replica_num": replica_num,
            "job_num": job_num,
        }
        if after is not None:
            params["after"] = after.isoformat()
        if before is not None:
            params["before"] = before.isoformat()
        if limit is not None:
            params["limit"] = limit
        resp = self._request(
            f"/api/project/{project_name}/metrics/job/{run_name}",
            method="GET",
            params=params,
        )
        return validate_extra_ignore(JobMetrics, resp.json())
