import pytest
from pydantic import ValidationError

from dstack._internal.core.compatibility.runs import get_run_spec_excludes
from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.configurations import (
    ServiceConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.profiles import (
    CreationPolicy,
    Profile,
    RetryEvent,
    SpotPolicy,
)
from dstack._internal.core.models.runs import (
    JobStatus,
    JobTerminationReason,
    RunSpec,
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


def test_unset_task_nodes_are_excluded_for_compatibility():
    configuration = TaskConfiguration(commands=["true"])

    configuration_excludes = get_run_spec_excludes(RunSpec(configuration=configuration)).get(
        "configuration"
    )

    assert isinstance(configuration_excludes, dict)
    assert configuration_excludes["nodes"] is True


def test_unset_service_groups_are_excluded_for_compatibility():
    configuration = ServiceConfiguration(commands=["true"], port=8000)

    configuration_excludes = get_run_spec_excludes(RunSpec(configuration=configuration)).get(
        "configuration"
    )

    assert isinstance(configuration_excludes, dict)
    assert configuration_excludes["groups"] is True


def test_set_service_groups_are_not_excluded():
    configuration = ServiceConfiguration(port=8000, groups=[{"replicas": 1, "commands": ["true"]}])

    configuration_excludes = get_run_spec_excludes(RunSpec(configuration=configuration)).get(
        "configuration"
    )

    assert not isinstance(configuration_excludes, dict) or "groups" not in configuration_excludes


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


def _service_run_spec_dict(router_type=None, retry=None, top_level_extras=None):
    """Build a minimal RunSpec dict for a service.

    `router_type`: None | "sglang" | "dynamo" — controls whether/how the
    second replica group has a router field.
    `retry`: optional dict passed as `profile.retry`.
    `top_level_extras`: optional dict merged into the service configuration.
    """
    replicas = [{"name": "worker", "commands": ["echo hi"], "count": 1}]
    if router_type is not None:
        replicas.append(
            {
                "name": "router",
                "router": {"type": router_type},
                "commands": ["echo router"],
                "count": 1,
            }
        )
    configuration = {
        "type": "service",
        "port": 8000,
        "replicas": replicas,
    }
    if top_level_extras:
        configuration.update(top_level_extras)
    profile = {"name": "default"}
    if retry is not None:
        profile["retry"] = retry
    return {
        "run_name": "test-run",
        "repo_id": "test-repo",
        "configuration_path": "dstack.yaml",
        "configuration": configuration,
        "profile": profile,
        "ssh_key_pub": "ssh-rsa AAAA...",
        "repo_data": {"repo_type": "virtual"},
    }


class TestDynamoNoRetryValidator:
    def test_dynamo_router_with_retry_at_profile_level_is_rejected(self):
        spec = _service_run_spec_dict(
            router_type="dynamo",
            retry={"on_events": ["error"]},
        )
        with pytest.raises(ValidationError, match="Dynamo"):
            RunSpec.model_validate(spec)

    def test_dynamo_router_with_retry_in_configuration_is_rejected(self):
        # retry can also be specified at configuration level; _merged_profile
        # folds it into merged_profile.retry, so the validator should still
        # catch it.
        spec = _service_run_spec_dict(
            router_type="dynamo",
            top_level_extras={"retry": {"on_events": ["error"]}},
        )
        with pytest.raises(ValidationError, match="Dynamo"):
            RunSpec.model_validate(spec)

    def test_dynamo_router_without_retry_is_accepted(self):
        spec = _service_run_spec_dict(router_type="dynamo", retry=None)
        # Should not raise:
        RunSpec.model_validate(spec)

    def test_sglang_router_with_retry_is_accepted(self):
        spec = _service_run_spec_dict(
            router_type="sglang",
            retry={"on_events": ["error"]},
        )
        # SGLang services are unaffected by the validator.
        RunSpec.model_validate(spec)

    def test_service_without_router_with_retry_is_accepted(self):
        spec = _service_run_spec_dict(router_type=None, retry={"on_events": ["error"]})
        RunSpec.model_validate(spec)

    def test_non_service_run_with_retry_is_accepted(self):
        # Validator is service-only. A task or dev-environment with retry
        # shouldn't be flagged regardless of the rest of the spec.
        spec = {
            "run_name": "test-run",
            "repo_id": "test-repo",
            "configuration_path": "dstack.yaml",
            "configuration": {
                "type": "task",
                "commands": ["echo hi"],
            },
            "profile": {"name": "default", "retry": {"on_events": ["error"]}},
            "ssh_key_pub": "ssh-rsa AAAA...",
            "repo_data": {"repo_type": "virtual"},
        }
        RunSpec.model_validate(spec)


class TestRunSpec:
    @pytest.mark.parametrize(
        "spec",
        [
            pytest.param(
                {"configuration": {"type": "dev-environment", "new_prop": 1}}, id="configuration"
            ),
            pytest.param(
                {
                    "configuration": {"type": "dev-environment"},
                    "profile": {"name": "default", "new_prop": 1},
                },
                id="profile",
            ),
            pytest.param(
                {
                    "configuration": {
                        "type": "dev-environment",
                        "resources": {"gpu": {"name": ["A100"], "new_prop": 1}},
                    }
                },
                id="nested-in-configuration",
            ),
            pytest.param(
                {"configuration": {"type": "dev-environment"}, "new_prop": 1}, id="top-level"
            ),
        ],
    )
    def test_extra_ignored_on_read_path(self, spec: dict):
        validate_extra_ignore(RunSpec, spec)
        with pytest.raises(ValidationError, match="new_prop"):
            RunSpec.model_validate(spec)

    def test_configuration_profile_params_override_profile(self):
        spec = RunSpec.model_validate(
            {
                "configuration": {"type": "dev-environment", "spot_policy": "spot"},
                "profile": {"name": "default", "spot_policy": "on-demand", "max_price": 1.5},
            }
        )
        assert spec.merged_profile.spot_policy == SpotPolicy.SPOT
        assert spec.merged_profile.max_price == 1.5
        assert spec.merged_profile.creation_policy == CreationPolicy.REUSE_OR_CREATE

    def test_merging_does_not_mutate_the_passed_profile(self):
        profile = Profile(name="default", spot_policy=SpotPolicy.ONDEMAND)
        spec = RunSpec.model_validate(
            {
                "configuration": {"type": "dev-environment", "spot_policy": "spot"},
                "profile": profile,
            }
        )
        assert spec.merged_profile.spot_policy == SpotPolicy.SPOT
        assert profile.spot_policy == SpotPolicy.ONDEMAND

    def test_missing_configuration_rejected(self):
        with pytest.raises(ValidationError, match="configuration"):
            validate_extra_ignore(RunSpec, {})
