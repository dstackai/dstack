from dstack._internal.cli.utils.preset import get_endpoint_presets_table
from dstack._internal.core.models.configurations import ServiceConfiguration
from dstack._internal.core.models.endpoint_presets import (
    EndpointPreset,
    EndpointPresetRecipe,
    EndpointPresetValidation,
    EndpointPresetValidationReplica,
)


class TestGetEndpointPresetsTable:
    def test_shows_single_group_preset(self):
        preset = _endpoint_preset(
            model="Qwen/Qwen3-0.6B",
            recipe_id="vllm-a40",
            service={"resources": {"gpu": "nvidia:16GB"}},
        )

        table = get_endpoint_presets_table([preset])

        assert [column.header for column in table.columns] == ["MODEL", "GPU"]
        assert table.columns[0]._cells == ["[bold]Qwen/Qwen3-0.6B[/]"]
        assert table.columns[1]._cells == [
            "nvidia:16GB:1..",
        ]

    def test_verbose_shows_full_resources(self):
        preset = _endpoint_preset(
            model="Qwen/Qwen3-0.6B",
            recipe_id="vllm-a40",
            service={"resources": {"gpu": "nvidia:16GB"}},
        )

        table = get_endpoint_presets_table([preset], verbose=True)

        assert [column.header for column in table.columns] == ["MODEL", "RESOURCES"]
        assert table.columns[0]._cells == ["[bold]Qwen/Qwen3-0.6B[/]"]
        assert table.columns[1]._cells == [
            "cpu=2.. mem=8GB.. disk=100GB.. gpu=nvidia:16GB:1..",
        ]

    def test_shows_recipe_model_when_it_differs_from_preset_base(self):
        preset = _endpoint_preset(
            model="Qwen/Qwen3-0.6B",
            recipe_id="vllm-a40",
            recipe_model="groxaxo/Qwen3-0.6B-GPTQ-4Bit",
            service={"resources": {"gpu": "nvidia:16GB"}},
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == [
            "[bold]Qwen/Qwen3-0.6B[/]",
            "   repo=groxaxo/Qwen3-0.6B-GPTQ-4Bit",
        ]
        assert table.columns[1]._cells == [
            "nvidia:16GB:1..",
            "",
        ]

    def test_shows_single_implicit_group_once_even_with_multiple_tested_replicas(self):
        preset = _endpoint_preset(
            model="Qwen/Qwen3-0.6B",
            recipe_id="vllm-a40",
            service={"resources": {"gpu": "nvidia:16GB"}},
            validation_replicas=[
                {
                    "resources": [
                        _exact_resources(),
                        _exact_resources(),
                    ]
                }
            ],
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == ["[bold]Qwen/Qwen3-0.6B[/]"]
        assert table.columns[1]._cells == [
            "nvidia:16GB:1..",
        ]

    def test_shows_grouped_replica_specs(self):
        preset = _endpoint_preset(
            model="Qwen/Qwen3-30B-A3B",
            recipe_id="pd-l4",
            service={
                "replicas": [
                    {
                        "name": "router",
                        "count": 1,
                        "commands": ["python router.py"],
                        "resources": {"cpu": 4},
                    },
                    {
                        "name": "worker",
                        "count": 2,
                        "commands": ["vllm serve Qwen/Qwen3-30B-A3B"],
                        "resources": {"gpu": "nvidia:24GB"},
                    },
                ]
            },
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == [
            "[bold]Qwen/Qwen3-30B-A3B[/]",
            "[secondary]   group=router[/]",
            "[secondary]   group=worker[/]",
        ]
        assert table.columns[1]._cells == [
            "",
            "-",
            "nvidia:24GB:1..",
        ]

    def test_groups_multiple_recipes_by_model(self):
        preset = EndpointPreset(
            base="Qwen/Qwen3-0.6B",
            recipes=[
                _endpoint_preset(
                    model="Qwen/Qwen3-0.6B",
                    recipe_id="vllm-a40",
                    service={"resources": {"gpu": "nvidia:16GB"}},
                ).recipes[0],
                _endpoint_preset(
                    model="Qwen/Qwen3-0.6B",
                    recipe_id="vllm-l4",
                    service={"resources": {"gpu": "nvidia:24GB"}},
                ).recipes[0],
            ],
        )

        table = get_endpoint_presets_table([preset])

        assert table.columns[0]._cells == [
            "[bold]Qwen/Qwen3-0.6B[/]",
            "[secondary]   recipe=0[/]",
            "[secondary]   recipe=1[/]",
        ]
        assert table.columns[1]._cells == [
            "",
            "nvidia:16GB:1..",
            "nvidia:24GB:1..",
        ]


def _endpoint_preset(
    *,
    model: str,
    recipe_id: str,
    service: dict,
    validation_replicas: list[dict] | None = None,
    recipe_model: str | None = None,
) -> EndpointPreset:
    service_data = {
        "type": "service",
        "port": 8000,
        "model": model,
        **service,
    }
    if "replicas" not in service_data:
        service_data["commands"] = [f"vllm serve {model}"]
    return EndpointPreset(
        base=model,
        recipes=[
            EndpointPresetRecipe(
                id=recipe_id,
                model=recipe_model or model,
                service=ServiceConfiguration.parse_obj(service_data),
                validations=[
                    EndpointPresetValidation(
                        replicas=[
                            EndpointPresetValidationReplica.parse_obj(replica)
                            for replica in (
                                validation_replicas or [{"resources": [_exact_resources()]}]
                            )
                        ]
                    )
                ],
            )
        ],
    )


def _exact_resources() -> dict:
    return {
        "cpu": 9,
        "memory": "50GB",
        "disk": "60GB",
        "gpu": {"name": "A40", "memory": "48GB", "count": 1},
    }
