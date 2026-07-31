"""
Rejection parity: input that pydantic v1 refuses must still be refused under v2.

Two rules:

- Assert only that validation raised. Never assert on the message text: v2 rewords errors by
  design, so a message assertion would fail for a reason we do not care about. The `dstack apply`
  error UX gets reviewed by hand instead.
- Inputs live inline, not in fixture files. Nothing is generated from them, they are one or two
  keys each, and a file per case would add indirection with no payoff.
"""

from typing import Any, Callable

import pytest
import yaml
from pydantic import ValidationError

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import parse_apply_configuration
from dstack._internal.server.schemas.volumes import CreateVolumeRequest
from tests._internal.pydantic_compat.compat import parse_forbid_extra

_VALID_TASK = "type: task\ncommands: [echo hi]\n"


def _task(extra_yaml: str) -> Any:
    return yaml.safe_load(_VALID_TASK + extra_yaml)


# name -> (parser, input, exception). Each input is rejected by v1 today; the test pins that it
# stays rejected. The production configuration parser wraps pydantic's error in ConfigurationError.
REJECTED_INPUTS: dict[str, tuple[Callable, Any, type[Exception]]] = {
    # A mistyped key must not be silently ignored — this is the whole point of `extra="forbid"`,
    # and the v2 `CoreModel` reaches it through a per-call override that could leak.
    "config_unknown_key": (
        parse_apply_configuration,
        _task("comands: [oops]\n"),
        ConfigurationError,
    ),
    "request_unknown_key": (
        CreateVolumeRequest.model_validate,
        {
            "configuration": {"type": "volume", "name": "v", "backend": "aws", "region": "r"},
            "unexpected": 1,
        },
        ValidationError,
    ),
    # Reversed ranges: caught by a validator, not by the type, so a dropped validator during the
    # `__get_pydantic_core_schema__` port would make these start passing.
    "resources_cpu_reversed_range": (
        parse_apply_configuration,
        _task("resources:\n  cpu: 8..2\n"),
        ConfigurationError,
    ),
    "resources_memory_reversed_range": (
        parse_apply_configuration,
        _task("resources:\n  memory: 32GB..8GB\n"),
        ConfigurationError,
    ),
    # Custom-type parsing: `Duration.parse` rejects unknown units and non-numeric input.
    "duration_bad_unit": (
        parse_apply_configuration,
        _task("max_duration: 5 years\n"),
        ConfigurationError,
    ),
    # An unknown discriminator tag. `BaseApplyConfiguration` declares `discriminator="type"`, so
    # the error names the tag instead of accumulating one failure per arm.
    "unknown_config_type": (
        parse_apply_configuration,
        {"type": "not-a-real-type"},
        ConfigurationError,
    ),
}


class TestRejectionParity:
    @pytest.mark.parametrize("name", sorted(REJECTED_INPUTS))
    def test_still_rejected(self, name):
        parser, data, exception = REJECTED_INPUTS[name]
        with pytest.raises(exception):
            parser(data)


class TestExtraHandlingIsNotAccidentallyRelaxed:
    """
    A guard on the mechanism rather than on any one model.

    `parse_forbid_extra` must keep forbidding. If the v2 rewrite routes request bodies through
    `parse_ignore_extra` by mistake, every case above would still pass while user typos quietly
    stopped being reported — so assert the forbidding helper actually rejects.
    """

    def test_forbid_extra_rejects_an_unknown_field(self):
        body = {
            "configuration": {
                "type": "volume",
                "name": "v",
                "backend": "aws",
                "region": "r",
                "size": "1GB",
            },
            "unexpected": 1,
        }
        with pytest.raises(ValidationError):
            parse_forbid_extra(CreateVolumeRequest, body)
