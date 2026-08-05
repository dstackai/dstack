from typing import Any

import pytest
from pydantic import ValidationError

from dstack._internal.core.models.common import validate_extra_ignore
from dstack._internal.core.models.fleets import FleetConfiguration, FleetNodesSpec, FleetSpec
from dstack._internal.core.models.profiles import Profile, SpotPolicy


class TestFleetConfiguration:
    @pytest.mark.parametrize(
        ["input_nodes", "expected_nodes"],
        [
            pytest.param(
                1,
                FleetNodesSpec(
                    min=1,
                    target=1,
                    max=1,
                ),
                id="int",
            ),
            pytest.param(
                "1..2",
                FleetNodesSpec(
                    min=1,
                    target=1,
                    max=2,
                ),
                id="closed-range",
            ),
            pytest.param(
                "..2",
                FleetNodesSpec(
                    min=0,
                    target=0,
                    max=2,
                ),
                id="range-without-min",
            ),
            pytest.param(
                "1..",
                FleetNodesSpec(
                    min=1,
                    target=1,
                    max=None,
                ),
                id="range-without-max",
            ),
            pytest.param(
                {
                    "min": 1,
                    "max": 2,
                },
                FleetNodesSpec(
                    min=1,
                    target=1,
                    max=2,
                ),
                id="dict-without-target",
            ),
            pytest.param(
                {
                    "min": 1,
                    "target": 2,
                    "max": 3,
                },
                FleetNodesSpec(
                    min=1,
                    target=2,
                    max=3,
                ),
                id="dict-with-all-attributes",
            ),
            pytest.param(
                {
                    "target": 2,
                    "max": 3,
                },
                FleetNodesSpec(
                    min=0,
                    target=2,
                    max=3,
                ),
                id="dict-without-min",
            ),
            pytest.param(
                {},
                FleetNodesSpec(
                    min=0,
                    target=0,
                    max=None,
                ),
                id="dict-empty",
            ),
        ],
    )
    def test_parses_nodes(self, input_nodes: Any, expected_nodes: FleetNodesSpec):
        configuration_input = {
            "type": "fleet",
            "nodes": input_nodes,
        }
        configuration = FleetConfiguration.model_validate(configuration_input)
        assert configuration.nodes == expected_nodes

    @pytest.mark.parametrize(
        ["input_nodes"],
        [
            pytest.param("2..1", id="min-gt-max"),
            pytest.param({"min": -1}, id="negative-min"),
            pytest.param({"target": -1}, id="negative-target"),
            pytest.param({"target": 2, "max": 1}, id="target-gt-max"),
            pytest.param({"min": 2, "max": 1}, id="min-gt-max"),
            pytest.param({"min": 2, "target": 1}, id="min-gt-target"),
        ],
    )
    def test_rejects_nodes(self, input_nodes: Any):
        configuration_input = {
            "type": "fleet",
            "nodes": input_nodes,
        }
        with pytest.raises(ValidationError):
            FleetConfiguration.model_validate(configuration_input)


class TestFleetSpec:
    @pytest.mark.parametrize(
        "spec",
        [
            pytest.param(
                {
                    "configuration": {"type": "fleet", "new_prop": 1},
                    "profile": {"name": "default"},
                },
                id="configuration",
            ),
            pytest.param(
                {
                    "configuration": {"type": "fleet"},
                    "profile": {"name": "default", "new_prop": 1},
                },
                id="profile",
            ),
            pytest.param(
                {
                    "configuration": {
                        "type": "fleet",
                        "resources": {"gpu": {"name": ["A100"], "new_prop": 1}},
                    },
                    "profile": {"name": "default"},
                },
                id="nested-in-configuration",
            ),
            pytest.param(
                {
                    "configuration": {"type": "fleet"},
                    "profile": {"name": "default"},
                    "new_prop": 1,
                },
                id="top-level",
            ),
        ],
    )
    def test_extra_ignored_on_read_path(self, spec: dict):
        validate_extra_ignore(FleetSpec, spec)
        with pytest.raises(ValidationError, match="new_prop"):
            FleetSpec.model_validate(spec)

    def test_configuration_profile_params_override_profile(self):
        spec = FleetSpec.model_validate(
            {
                "configuration": {"type": "fleet", "reservation": "conf-reservation"},
                "profile": {"name": "default", "reservation": "profile-reservation"},
            }
        )
        assert spec.merged_profile.reservation == "conf-reservation"
        assert spec.merged_profile.spot_policy == SpotPolicy.ONDEMAND
        assert spec.merged_profile.retry is False

    def test_merging_does_not_mutate_the_passed_profile(self):
        profile = Profile(name="default", spot_policy=SpotPolicy.ONDEMAND)
        spec = FleetSpec.model_validate(
            {"configuration": {"type": "fleet", "spot_policy": "spot"}, "profile": profile}
        )
        assert spec.merged_profile.spot_policy == SpotPolicy.SPOT
        assert profile.spot_policy == SpotPolicy.ONDEMAND

    @pytest.mark.parametrize(
        ["spec", "missing_field"],
        [
            pytest.param({"configuration": {"type": "fleet"}}, "profile", id="missing-profile"),
            pytest.param({"profile": {"name": "default"}}, "configuration", id="missing-conf"),
        ],
    )
    def test_missing_required_fields_rejected(self, spec: dict, missing_field: str):
        with pytest.raises(ValidationError, match=missing_field):
            validate_extra_ignore(FleetSpec, spec)
