from types import SimpleNamespace
from typing import cast

import pytest

from dstack._internal.cli.commands.apply import validate_no_recreate_configuration
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.configurations import (
    AnyApplyConfiguration,
    ApplyConfigurationType,
)
from tests._internal.cli.common import run_dstack_cli


def _configuration(
    configuration_type: ApplyConfigurationType,
    *,
    name: str | None,
) -> AnyApplyConfiguration:
    return cast(
        AnyApplyConfiguration,
        SimpleNamespace(type=configuration_type.value, name=name),
    )


def test_help_documents_no_recreate(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_dstack_cli(["apply", "--help"]) == 0

    normalized_output = " ".join(capsys.readouterr().out.split())
    assert "[--force | --no-recreate]" in normalized_output
    assert (
        "Fail instead of changing an active run; unchanged active runs are no-op"
        in normalized_output
    )


def test_no_recreate_is_mutually_exclusive_with_force(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run_dstack_cli(["apply", "--force", "--no-recreate"]) == 2

    assert "not allowed with argument --force" in capsys.readouterr().err


@pytest.mark.parametrize(
    "configuration_type",
    [
        ApplyConfigurationType.FLEET,
        ApplyConfigurationType.GATEWAY,
        ApplyConfigurationType.VOLUME,
    ],
)
def test_no_recreate_rejects_non_run_configurations(
    configuration_type: ApplyConfigurationType,
) -> None:
    configuration = _configuration(configuration_type, name="resource")

    with pytest.raises(CLIError, match="only supported for run configurations"):
        validate_no_recreate_configuration(configuration)


@pytest.mark.parametrize(
    "configuration_type",
    [
        ApplyConfigurationType.DEV_ENVIRONMENT,
        ApplyConfigurationType.TASK,
        ApplyConfigurationType.SERVICE,
    ],
)
def test_no_recreate_accepts_named_run_configurations(
    configuration_type: ApplyConfigurationType,
) -> None:
    configuration = _configuration(configuration_type, name="dev-run")

    validate_no_recreate_configuration(configuration)


def test_no_recreate_rejects_unnamed_run_configuration() -> None:
    configuration = _configuration(ApplyConfigurationType.DEV_ENVIRONMENT, name=None)

    with pytest.raises(CLIError, match="requires a named run"):
        validate_no_recreate_configuration(configuration)
