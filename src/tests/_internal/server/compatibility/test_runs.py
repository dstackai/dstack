from typing import Optional, Union

import pytest
from packaging.version import Version
from pydantic_core import to_json

from dstack._internal.core.models.common import CoreModel, validate_json_extra_ignore
from dstack._internal.core.models.configurations import (
    AnyRunConfiguration,
    DevEnvironmentConfiguration,
    ServiceConfiguration,
    TaskConfiguration,
    parse_run_configuration,
)
from dstack._internal.core.models.resources import Range
from dstack._internal.server.compatibility.runs import (
    is_run_plan_for_offers_only,
    patch_run_spec,
)
from dstack._internal.server.testing.common import get_run_spec


class _Legacy021ReplicaGroup(CoreModel):
    """0.21-shaped group: size is `count`, no `groups` parent field."""

    count: Range[int]
    commands: list[str] = []


class _Legacy021Service(CoreModel):
    """Stand-in for a 0.21 client that does not know `groups`."""

    commands: list[str] = []
    image: Optional[str] = None
    replicas: Optional[Union[list[_Legacy021ReplicaGroup], Range[int]]] = None


def _grouped_service() -> ServiceConfiguration:
    configuration = parse_run_configuration(
        {
            "type": "service",
            "port": 8000,
            "groups": [
                {"replicas": 1, "commands": ["a"]},
                {"replicas": 2, "commands": ["b"]},
            ],
        }
    )
    assert isinstance(configuration, ServiceConfiguration)
    return configuration


class TestPatchRunSpecReplicaGroups:
    @pytest.mark.parametrize(
        "client_version",
        [Version("0.20.7"), Version("0.21.0"), Version("0.21.2")],
    )
    def test_downgrades_groups_for_clients_without_them(self, client_version):
        run_spec = get_run_spec(repo_id="test", configuration=_grouped_service())

        patch_run_spec(run_spec, client_version)

        configuration = run_spec.configuration
        assert configuration.groups is None
        assert [group["count"] for group in configuration.replicas] == [
            {"min": 1, "max": 1},
            {"min": 2, "max": 2},
        ]
        # `to_json` is how the server actually renders a response, so this is
        # exactly the payload an old client has to parse.
        validate_json_extra_ignore(_Legacy021Service, to_json(configuration))

    @pytest.mark.parametrize("client_version", [Version("0.21.3"), Version("0.22.0"), None])
    def test_keeps_groups_for_clients_that_support_them(self, client_version):
        run_spec = get_run_spec(repo_id="test", configuration=_grouped_service())

        patch_run_spec(run_spec, client_version)

        assert run_spec.configuration.replicas is None
        assert [group.replicas for group in run_spec.configuration.groups] == [
            Range[int](min=1, max=1),
            Range[int](min=2, max=2),
        ]

    def test_leaves_a_service_without_groups_alone(self):
        configuration = parse_run_configuration(
            {"type": "service", "port": 8000, "commands": ["x"], "replicas": 2}
        )
        run_spec = get_run_spec(repo_id="test", configuration=configuration)

        patch_run_spec(run_spec, Version("0.21.0"))

        assert run_spec.configuration.groups is None
        assert run_spec.configuration.replicas == Range[int](min=2, max=2)


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
