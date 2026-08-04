from unittest.mock import MagicMock

import pytest

from dstack._internal.cli.commands.metrics import _get_job, _get_job_metrics
from dstack._internal.cli.utils.metrics import MAX_SAMPLES
from dstack._internal.core.errors import CLIError
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
    def test_defaults_to_the_first_job_of_the_first_replica(self):
        """Same shape as `dstack logs`: one job, --replica/--job to pick another."""
        job = _get_job(_run(replicas=3), replica_num=0, job_num=0)
        assert (job.job_spec.replica_num, job.job_spec.job_num) == (0, 0)

    def test_selects_by_replica_and_job(self):
        job = _get_job(_run(replicas=3, jobs_per_replica=2), replica_num=2, job_num=1)
        assert (job.job_spec.replica_num, job.job_spec.job_num) == (2, 1)

    def test_unknown_job_is_an_error(self):
        with pytest.raises(CLIError, match="replica=7"):
            _get_job(_run(replicas=3), replica_num=7, job_num=0)


class TestMetricsRequest:
    def test_limit_is_sent_explicitly(self):
        """The endpoint declares `limit: int = 1`, not Optional, so omitting it caps the
        response at a single sample -- which renders as one glyph however long the run has
        been up, and looks plausible rather than broken."""
        api = MagicMock()
        api.project = "main"
        api.client.metrics.get_job_metrics.return_value = JobMetrics(metrics=[])
        run = _run()
        _get_job_metrics(api, run, run._run.jobs[0])
        kwargs = api.client.metrics.get_job_metrics.call_args.kwargs
        assert kwargs["limit"] == MAX_SAMPLES
        assert "after" not in kwargs and "before" not in kwargs
