from typing import Any

import pytest
from pydantic import ValidationError

from dstack._internal.core.models.fleets import FleetConfiguration, FleetNodesSpec


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
        configuration = FleetConfiguration.parse_obj(configuration_input)
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
            FleetConfiguration.parse_obj(configuration_input)
