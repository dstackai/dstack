import pytest
from pydantic import ValidationError

from dstack._internal.core.models.runs import RunSpec


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
            RunSpec.parse_obj(spec)

    def test_dynamo_router_with_retry_in_configuration_is_rejected(self):
        # retry can also be specified at configuration level; _merged_profile
        # folds it into merged_profile.retry, so the validator should still
        # catch it.
        spec = _service_run_spec_dict(
            router_type="dynamo",
            top_level_extras={"retry": {"on_events": ["error"]}},
        )
        with pytest.raises(ValidationError, match="Dynamo"):
            RunSpec.parse_obj(spec)

    def test_dynamo_router_without_retry_is_accepted(self):
        spec = _service_run_spec_dict(router_type="dynamo", retry=None)
        # Should not raise:
        RunSpec.parse_obj(spec)

    def test_sglang_router_with_retry_is_accepted(self):
        spec = _service_run_spec_dict(
            router_type="sglang",
            retry={"on_events": ["error"]},
        )
        # SGLang services are unaffected by the validator.
        RunSpec.parse_obj(spec)

    def test_service_without_router_with_retry_is_accepted(self):
        spec = _service_run_spec_dict(router_type=None, retry={"on_events": ["error"]})
        RunSpec.parse_obj(spec)

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
        RunSpec.parse_obj(spec)
