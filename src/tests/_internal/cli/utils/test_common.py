from unittest.mock import Mock

from dstack._internal.cli.utils.common import format_job_display_name
from dstack._internal.core.models.runs import Job, JobSpec


def create_mock_job(replica_num: int, job_num: int) -> Job:
    job_spec = Mock(spec=JobSpec)
    job_spec.replica_num = replica_num
    job_spec.job_num = job_num

    job = Mock(spec=Job)
    job.job_spec = job_spec
    return job


class TestFormatJobDisplayName:
    def test_multiple_jobs_single_replica(self):
        jobs = [
            create_mock_job(replica_num=0, job_num=0),
            create_mock_job(replica_num=0, job_num=1),
            create_mock_job(replica_num=0, job_num=2),
        ]
        current_job = jobs[1]  # job_num=1

        result = format_job_display_name(jobs, current_job)

        assert result == "  job=1"

    def test_single_job_multiple_replicas(self):
        jobs = [
            create_mock_job(replica_num=0, job_num=0),
            create_mock_job(replica_num=1, job_num=0),
            create_mock_job(replica_num=2, job_num=0),
        ]
        current_job = jobs[1]  # replica_num=1

        result = format_job_display_name(jobs, current_job)

        assert result == "  replica=1"

    def test_multiple_jobs_multiple_replicas(self):
        jobs = [
            create_mock_job(replica_num=0, job_num=0),
            create_mock_job(replica_num=0, job_num=1),
            create_mock_job(replica_num=1, job_num=0),
            create_mock_job(replica_num=1, job_num=1),
        ]
        current_job = jobs[3]  # replica_num=1, job_num=1

        result = format_job_display_name(jobs, current_job)

        assert result == "  replica=1 job=1"
