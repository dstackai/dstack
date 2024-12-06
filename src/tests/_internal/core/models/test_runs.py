from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
)


def test_run_to_job_termination_reason_works_with_all_enum_variants():
    for run_termination_reason in RunTerminationReason:
        job_termination_reason = run_termination_reason.to_job_termination_reason()
        assert isinstance(job_termination_reason, JobTerminationReason)


def test_run_termination_reason_to_status_works_with_all_enum_variants():
    for run_termination_reason in RunTerminationReason:
        run_status = run_termination_reason.to_status()
        assert isinstance(run_status, RunStatus)


def test_job_termination_reason_to_status_works_with_all_enum_varians():
    for job_termination_reason in JobTerminationReason:
        job_status = job_termination_reason.to_status()
        assert isinstance(job_status, JobStatus)
