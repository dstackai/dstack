from dstack._internal.cli.utils.preset import get_endpoint_presets_table
from dstack._internal.core.models.endpoint_presets import (
    EndpointPreset,
    EndpointPresetReplicaSpecGroup,
)


class TestGetEndpointPresetsTable:
    def test_shows_single_group_preset(self):
        preset = EndpointPreset(
            name="qwen-qwen3-0-6b",
            model="Qwen/Qwen3-0.6B",
            replica_spec_groups=[
                EndpointPresetReplicaSpecGroup.parse_obj(
                    {"name": "0", "replica_specs": [{"gpu": "16GB", "disk": "60GB"}]}
                )
            ],
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == ["qwen-qwen3-0-6b"]
        assert table.columns[1]._cells == ["Qwen/Qwen3-0.6B"]
        assert "gpu=16GB" in table.columns[2]._cells[0]
        assert "disk=60GB" in table.columns[2]._cells[0]

    def test_shows_grouped_replica_specs(self):
        preset = EndpointPreset(
            name="qwen-pd",
            model="Qwen/Qwen3-30B-A3B",
            replica_spec_groups=[
                EndpointPresetReplicaSpecGroup.parse_obj(
                    {"name": "router", "replica_specs": [{"cpu": 4}]}
                ),
                EndpointPresetReplicaSpecGroup.parse_obj(
                    {"name": "worker", "replica_specs": [{"gpu": "24GB"}, {"gpu": "24GB"}]}
                ),
            ],
        )

        table = get_endpoint_presets_table([preset])

        resources = table.columns[2]._cells[0]
        assert "router:" in resources
        assert "worker:" in resources
        assert "2x" in resources
        assert "gpu=24GB" in resources
