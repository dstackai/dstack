from typing import Optional

import pytest
from packaging.version import Version

from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    DevEnvironmentConfiguration,
    TaskConfiguration,
)
from dstack._internal.server.compatibility.runs import is_run_plan_for_offers_only
from dstack._internal.server.testing.common import get_run_spec

_OFFER_CLI_CONFIGURATION = TaskConfiguration(commands=[":"], image="scratch", user="root")


class TestIsRunPlanForOffersOnly:
    @pytest.mark.parametrize(
        ("configuration", "for_offers_only", "client_version", "expected"),
        [
            pytest.param(_OFFER_CLI_CONFIGURATION, True, Version("0.21.0"), True, id="flag-set"),
            pytest.param(
                DevEnvironmentConfiguration(),
                True,
                Version("0.21.0"),
                True,
                id="flag-set-for-any-configuration",
            ),
            pytest.param(
                _OFFER_CLI_CONFIGURATION,
                False,
                Version("0.20.30"),
                True,
                id="old-client-sends-offer-cli-configuration",
            ),
            pytest.param(
                TaskConfiguration(commands=["echo"], image="scratch"),
                False,
                Version("0.20.30"),
                False,
                id="old-client-sends-regular-task",
            ),
            pytest.param(
                DevEnvironmentConfiguration(),
                False,
                Version("0.20.30"),
                False,
                id="old-client-sends-configuration-without-commands",
            ),
            pytest.param(
                _OFFER_CLI_CONFIGURATION,
                False,
                Version("0.21.0"),
                False,
                id="new-client-does-not-rely-on-offer-cli-configuration",
            ),
            pytest.param(
                _OFFER_CLI_CONFIGURATION,
                False,
                None,
                False,
                id="dev-client-does-not-rely-on-offer-cli-configuration",
            ),
        ],
    )
    def test_returns_expected(
        self,
        configuration: AnyRunConfiguration,
        for_offers_only: bool,
        client_version: Optional[Version],
        expected: bool,
    ) -> None:
        run_spec = get_run_spec(repo_id="test-repo", configuration=configuration)
        assert (
            is_run_plan_for_offers_only(
                run_spec=run_spec,
                for_offers_only=for_offers_only,
                client_version=client_version,
            )
            is expected
        )
