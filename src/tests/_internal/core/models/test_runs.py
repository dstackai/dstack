from dstack._internal.core.models.profiles import RetryEvent
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


def test_job_termination_reason_to_status_works_with_all_enum_variants():
    for job_termination_reason in JobTerminationReason:
        job_status = job_termination_reason.to_status()
        assert isinstance(job_status, JobStatus)


def test_job_termination_reason_to_retry_event_works_with_all_enum_variants():
    for job_termination_reason in JobTerminationReason:
        retry_event = job_termination_reason.to_retry_event()
        assert retry_event is None or isinstance(retry_event, RetryEvent)


# Will fail if JobTerminationReason value is added without updating JobSubmission._get_error
def test_get_error_returns_expected_messages():
    # already handled and shown in status_message
    no_error_reasons = [
        JobTerminationReason.FAILED_TO_START_DUE_TO_NO_CAPACITY,
        JobTerminationReason.INTERRUPTED_BY_NO_CAPACITY,
        JobTerminationReason.WAITING_RUNNER_LIMIT_EXCEEDED,
        JobTerminationReason.TERMINATED_BY_USER,
        JobTerminationReason.DONE_BY_RUNNER,
        JobTerminationReason.ABORTED_BY_USER,
        JobTerminationReason.TERMINATED_BY_SERVER,
        JobTerminationReason.CONTAINER_EXITED_WITH_ERROR,
    ]

    for reason in JobTerminationReason:
        if reason.to_error() is None:
            # Fail no-error reason is not in the list
            assert reason in no_error_reasons


# Will fail if RunTerminationReason value is added without updating Run._get_error
def test_run_get_error_returns_none_for_specific_reasons():
    no_error_reasons = [
        RunTerminationReason.ALL_JOBS_DONE,
        RunTerminationReason.JOB_FAILED,
        RunTerminationReason.STOPPED_BY_USER,
        RunTerminationReason.ABORTED_BY_USER,
    ]

    for reason in RunTerminationReason:
        if reason.to_error() is None:
            # Fail no-error reason is not in the list
            assert reason in no_error_reasons
