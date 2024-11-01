import pytest

from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunStatus,
    RunTerminationReason,
    ServiceSpec,
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


def test_service_spec_full_url_from_full_url():
    spec = ServiceSpec(url="https://service.gateway.dstack.example")
    assert (
        spec.full_url(server_base_url="http://localhost:3000")
        == "https://service.gateway.dstack.example"
    )


@pytest.mark.parametrize(
    ("server_url", "service_path", "service_url"),
    [
        (
            "http://localhost:3000",
            "/proxy/services/main/service/",
            "http://localhost:3000/proxy/services/main/service/",
        ),
        (
            "http://localhost:3000/",
            "/proxy/services/main/service/",
            "http://localhost:3000/proxy/services/main/service/",
        ),
        (
            "http://localhost:3000/prefix",
            "/proxy/services/main/service/",
            "http://localhost:3000/prefix/proxy/services/main/service/",
        ),
    ],
)
def test_service_spec_full_url_from_path(server_url, service_path, service_url):
    assert ServiceSpec(url=service_path).full_url(server_base_url=server_url) == service_url
