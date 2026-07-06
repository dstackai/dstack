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
                    {
                        "name": "0",
                        "resources": {"gpu": "16GB"},
                        "tested_resources": [
                            {
                                "cpu": 9,
                                "memory": "50GB",
                                "disk": "60GB",
                                "gpu": {"name": "A40", "memory": "48GB", "count": 1},
                            }
                        ],
                    }
                )
            ],
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == ["qwen-qwen3-0-6b"]
        assert table.columns[1]._cells == ["Qwen/Qwen3-0.6B"]
        assert table.columns[2]._cells == [
            "cpu=2.. mem=8GB.. disk=100GB.. gpu=16GB:1..",
        ]

    def test_shows_single_implicit_group_once_even_with_multiple_tested_replicas(self):
        preset = EndpointPreset(
            name="qwen",
            model="Qwen/Qwen3-0.6B",
            replica_spec_groups=[
                EndpointPresetReplicaSpecGroup.parse_obj(
                    {
                        "name": "0",
                        "resources": {"gpu": "16GB"},
                        "tested_resources": [
                            {
                                "cpu": 9,
                                "memory": "50GB",
                                "disk": "60GB",
                                "gpu": {"name": "A40", "memory": "48GB", "count": 1},
                            },
                            {
                                "cpu": 9,
                                "memory": "50GB",
                                "disk": "60GB",
                                "gpu": {"name": "A40", "memory": "48GB", "count": 1},
                            },
                        ],
                    }
                )
            ],
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == ["qwen"]
        assert table.columns[1]._cells == ["Qwen/Qwen3-0.6B"]
        assert table.columns[2]._cells == [
            "cpu=2.. mem=8GB.. disk=100GB.. gpu=16GB:1..",
        ]

    def test_shows_grouped_replica_specs(self):
        preset = EndpointPreset(
            name="qwen-pd",
            model="Qwen/Qwen3-30B-A3B",
            replica_spec_groups=[
                EndpointPresetReplicaSpecGroup.parse_obj(
                    {
                        "name": "router",
                        "resources": {"cpu": 4},
                        "tested_resources": [
                            {"cpu": 8, "memory": "16GB", "disk": "100GB", "gpu": 0}
                        ],
                    }
                ),
                EndpointPresetReplicaSpecGroup.parse_obj(
                    {
                        "name": "worker",
                        "resources": {"gpu": "24GB"},
                        "tested_resources": [
                            {
                                "cpu": 14,
                                "memory": "64GB",
                                "disk": "200GB",
                                "gpu": {"name": "L4", "memory": "24GB", "count": 1},
                            },
                            {
                                "cpu": 14,
                                "memory": "64GB",
                                "disk": "200GB",
                                "gpu": {"name": "L4", "memory": "24GB", "count": 1},
                            },
                        ],
                    }
                ),
            ],
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == [
            "qwen-pd",
            "   group=router",
            "   group=worker",
        ]
        assert table.columns[1]._cells == ["Qwen/Qwen3-30B-A3B", "", ""]
        assert table.columns[2]._cells == [
            "",
            "cpu=4 mem=8GB.. disk=100GB..",
            "cpu=2.. mem=8GB.. disk=100GB.. gpu=24GB:1..",
        ]
