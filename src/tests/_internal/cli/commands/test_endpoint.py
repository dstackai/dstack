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
