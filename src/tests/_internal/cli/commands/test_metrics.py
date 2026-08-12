from unittest.mock import MagicMock

import pytest

from dstack._internal.cli.commands.metrics import _get_job_metrics, select_jobs
from dstack._internal.cli.utils.metrics import MAX_SAMPLES
from dstack._internal.core.models.metrics import JobMetrics


def _run(replicas: int = 1, jobs_per_replica: int = 1):
    run = MagicMock()
    run.name = "my-run"
    run._run.jobs = []
    for replica in range(replicas):
        for job_num in range(jobs_per_replica):
            job = MagicMock()
            job.job_spec.replica_num = replica
            job.job_spec.job_num = job_num
            run._run.jobs.append(job)
    return run


class TestJobSelection:
    @pytest.mark.parametrize(
        "replica,job_num,expected",
        [(None, None, 4), (0, None, 2), (None, 1, 2), (0, 1, 1), (9, None, 0)],
        ids=["all", "one-replica", "one-node", "both", "no-match"],
    )
    def test_filters(self, replica, job_num, expected):
        jobs = _run(replicas=2, jobs_per_replica=2)._run.jobs
        assert len(select_jobs(jobs, replica, job_num)) == expected


class TestMetricsRequest:
    def test_limit_is_sent_explicitly(self):
        api = MagicMock()
        api.project = "main"
        api.client.metrics.get_job_metrics.return_value = JobMetrics(metrics=[])
        run = _run()
        _get_job_metrics(api, run, run._run.jobs[0])
        kwargs = api.client.metrics.get_job_metrics.call_args.kwargs
        assert kwargs["limit"] == MAX_SAMPLES
        assert "after" not in kwargs and "before" not in kwargs
