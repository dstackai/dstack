import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dstack._internal.cli.services.endpoint_presets import EndpointPresetStore
from tests._internal.cli.common import run_dstack_cli
from tests._internal.cli.endpoint_presets import get_endpoint_preset_recipe

pytestmark = pytest.mark.windows


class TestEndpointPresetLocalCommands:
    def test_handles_keyboard_interrupt(self, tmp_path, capsys):
        configuration_path = tmp_path / "endpoint.dstack.yml"
        configuration_path.write_text(
            "type: endpoint\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )

        with (
            patch("dstack._internal.cli.main.get_ssh_client_info"),
            patch("dstack.api.Client.from_config"),
            patch(
                "dstack._internal.cli.commands.endpoint.create_endpoint_preset",
                side_effect=KeyboardInterrupt,
            ),
        ):
            exit_code = run_dstack_cli(
                ["endpoint", "preset", "create", "-f", str(configuration_path)],
                home_dir=tmp_path,
            )

        assert exit_code == 0
        assert "Operation interrupted by user" in capsys.readouterr().out

    def test_lists_and_deletes_recipe_without_api_client(self, tmp_path, capsys):
        recipe = get_endpoint_preset_recipe()
        EndpointPresetStore(tmp_path / ".dstack" / "presets").save(recipe)

        with patch("dstack.api.Client.from_config") as from_config:
            assert run_dstack_cli(["endpoint", "preset", "list"], home_dir=tmp_path) == 0
            from_config.assert_not_called()

        output = capsys.readouterr().out
        assert "Qwen/Qwen3.5-27B" in output
        assert "recipe=8f3a12c4" in output
        assert "repo=community/Qwen3.5-27B-GPTQ-Int4" in output
        assert "CONTEXT" in output
        assert "BENCHMARK" in output
        assert "32K" in output
        assert "42.1" in output
        assert "tok/s" in output
        assert "TTFT 108ms" in output
        assert "A6000:48GB:1" not in output

        assert run_dstack_cli(["endpoint", "preset", "list", "-v"], home_dir=tmp_path) == 0
        verbose_output = capsys.readouterr().out
        assert "hardware=" in verbose_output
        assert "api=" in verbose_output
        assert "n=16" in verbose_output
        assert "c=1" in verbose_output
        assert "1K->128" in verbose_output

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    [
                        "endpoint",
                        "preset",
                        "delete",
                        "--recipe",
                        recipe.id,
                        "-y",
                    ],
                    home_dir=tmp_path,
                )
                == 0
            )
            from_config.assert_not_called()

        assert EndpointPresetStore(tmp_path / ".dstack" / "presets").list() == []
        assert not (tmp_path / ".dstack" / "presets" / "models--Qwen--Qwen3.5-27B").exists()

    @pytest.mark.parametrize(
        "args",
        [
            ["endpoint", "preset", "--json"],
            ["endpoint", "preset", "list", "--json"],
        ],
    )
    def test_lists_complete_recipes_as_json(self, tmp_path, capsys, args):
        recipe = get_endpoint_preset_recipe()
        EndpointPresetStore(tmp_path / ".dstack" / "presets").save(recipe)

        assert run_dstack_cli(args, home_dir=tmp_path) == 0

        output = json.loads(capsys.readouterr().out)
        assert len(output["recipes"]) == 1
        data = output["recipes"][0]
        assert data["id"] == recipe.id
        assert data["context_length"] == 32768
        assert data["validations"][0]["benchmark"]["metrics"]["total_output_tokens"] == 2048

    def test_deletes_preset_without_api_client(self, tmp_path):
        recipe = get_endpoint_preset_recipe()
        store = EndpointPresetStore(tmp_path / ".dstack" / "presets")
        store.save(recipe)
        store.save(recipe.copy(update={"id": "01234567"}))

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    ["endpoint", "preset", "delete", recipe.base, "-y"],
                    home_dir=tmp_path,
                )
                == 0
            )
            from_config.assert_not_called()

        assert store.list() == []

    def test_merges_profile_configuration_and_cli_args(self, tmp_path):
        (tmp_path / ".dstack").mkdir()
        (tmp_path / ".dstack" / "profiles.yml").write_text(
            """profiles:
  - name: gpu
    default: true
    backends: [aws]
    regions: [profile-region]
    max_price: 0.25
    spot_policy: spot
"""
        )
        configuration_path = tmp_path / "endpoint.dstack.yml"
        configuration_path.write_text(
            """type: endpoint
name: file-name
model:
  base: Qwen/Qwen3.5-27B
regions: [file-region]
max_price: 0.5
env:
  - HF_TOKEN
"""
        )
        recipe = get_endpoint_preset_recipe()
        result = SimpleNamespace(
            recipe=recipe,
            path=tmp_path / "recipe.yaml",
            final_run_name="qwen-build-2",
        )

        with (
            patch("dstack.api.Client.from_config"),
            patch(
                "dstack._internal.cli.commands.endpoint.create_endpoint_preset",
                return_value=result,
            ) as create,
        ):
            exit_code = run_dstack_cli(
                [
                    "endpoint",
                    "preset",
                    "create",
                    "-f",
                    str(configuration_path),
                    "--name",
                    "cli-name",
                    "--backend",
                    "gcp",
                    "--max-price",
                    "0.75",
                    "--fleet",
                    "cli-fleet",
                    "--debug",
                ],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        configuration = create.call_args.kwargs["configuration"]
        assert configuration.name == "cli-name"
        assert configuration.backends == ["gcp"]
        assert configuration.regions == ["file-region"]
        assert configuration.max_price == 0.75
        assert configuration.spot_policy.value == "spot"
        assert [fleet.format() for fleet in configuration.fleets] == ["cli-fleet"]
        assert create.call_args.kwargs["debug"] is True

    def test_apply_passes_selected_profile(self, tmp_path):
        (tmp_path / ".dstack").mkdir()
        (tmp_path / ".dstack" / "profiles.yml").write_text(
            "profiles:\n  - name: gpu\n    max_price: 0.5\n"
        )
        configuration_path = tmp_path / "endpoint.dstack.yml"
        configuration_path.write_text(
            "type: endpoint\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\n"
        )

        with (
            patch("dstack.api.Client.from_config"),
            patch("dstack._internal.cli.commands.endpoint.apply_endpoint_preset") as apply,
        ):
            exit_code = run_dstack_cli(
                [
                    "endpoint",
                    "preset",
                    "apply",
                    "-f",
                    str(configuration_path),
                    "--profile",
                    "gpu",
                ],
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        assert apply.call_args.kwargs["profile_name"] == "gpu"
        assert apply.call_args.kwargs["configuration"].max_price == 0.5
