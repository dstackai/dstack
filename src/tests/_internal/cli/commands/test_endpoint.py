import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rich.console import Console
from rich.theme import Theme

from dstack._internal.cli.services.endpoints import output as endpoint_presets_utils
from dstack._internal.cli.services.endpoints.store import EndpointPresetStore
from tests._internal.cli.common import run_dstack_cli
from tests._internal.cli.endpoint_presets import get_endpoint_preset

pytestmark = pytest.mark.windows


class TestEndpointPresetLocalCommands:
    @pytest.fixture(autouse=True)
    def mock_ssh_client_info(self):
        with patch("dstack._internal.cli.main.get_ssh_client_info"):
            yield

    def test_formats_second_scale_ttft_without_scientific_notation(self):
        preset = get_endpoint_preset()
        ttft = preset.validations[0].benchmark.metrics.ttft_ms
        ttft.mean = 8148.3
        ttft.p50 = 8151.4
        ttft.p99 = 8334.2

        output = endpoint_presets_utils.format_endpoint_benchmark(preset, verbose=True)

        assert "TTFT 8.15s" in output
        assert "TTFT mean/p50/p99=8.15/8.15/8.33s" in output
        assert "e+03" not in output

    def test_preserves_benchmark_concurrency_at_narrow_width(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            endpoint_presets_utils,
            "console",
            Console(
                file=output,
                width=79,
                color_system=None,
                theme=Theme({"secondary": "grey58"}),
            ),
        )

        endpoint_presets_utils.print_endpoint_presets([get_endpoint_preset()])

        assert "concurrency=1" in "".join(output.getvalue().split())

    def test_prints_created_column(self, monkeypatch):
        output = StringIO()
        monkeypatch.setattr(
            endpoint_presets_utils,
            "console",
            Console(
                file=output,
                width=160,
                color_system=None,
                theme=Theme({"secondary": "grey58"}),
            ),
        )
        monkeypatch.setattr(endpoint_presets_utils, "pretty_date", lambda _: "2 months ago")

        endpoint_presets_utils.print_endpoint_presets([get_endpoint_preset()])

        assert "CREATED" in output.getvalue()
        assert "2 months ago" in output.getvalue()

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

    def test_lists_and_deletes_preset_without_api_client(self, tmp_path, capsys):
        preset = get_endpoint_preset()
        EndpointPresetStore(tmp_path / ".dstack" / "presets").save(preset)
        list_output = StringIO()

        with (
            patch("dstack.api.Client.from_config") as from_config,
            patch.object(
                endpoint_presets_utils,
                "console",
                Console(
                    file=list_output,
                    width=160,
                    color_system=None,
                    theme=Theme({"secondary": "grey58"}),
                ),
            ),
            patch.object(
                endpoint_presets_utils, "pretty_date", return_value="2 months ago"
            ) as pretty_date,
        ):
            assert run_dstack_cli(["endpoint", "preset", "list"], home_dir=tmp_path) == 0
            from_config.assert_not_called()
            pretty_date.assert_called_once_with(preset.created_at)

        output = list_output.getvalue()
        assert "Qwen/Qwen3.5-27B" in output
        assert "preset=8f3a12c4" in output
        assert "repo=community/Qwen3.5-27B-GPTQ-Int4" in output
        assert "CONTEXT" in output
        assert "BENCHMARK" in output
        assert "32K" in output
        assert "42.1" in output
        assert "concurrency=1" in "".join(output.split())
        assert "tok/s" in output
        assert "TTFT" in output
        assert "108ms" in output
        assert "A6000:48GB:1" not in output

        assert run_dstack_cli(["endpoint", "preset", "list", "-v"], home_dir=tmp_path) == 0
        verbose_output = capsys.readouterr().out
        assert "hardware=" in verbose_output
        assert "api=" in verbose_output
        assert "n=16" in verbose_output
        assert "concurrency=1" in "".join(verbose_output.split())
        assert "1K->128" in verbose_output

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    [
                        "endpoint",
                        "preset",
                        "delete",
                        preset.id,
                        "-y",
                    ],
                    home_dir=tmp_path,
                )
                == 0
            )
            from_config.assert_not_called()

        assert EndpointPresetStore(tmp_path / ".dstack" / "presets").list() == []
        assert not (tmp_path / ".dstack" / "presets" / "models--Qwen--Qwen3.5-27B").exists()

    def test_gets_complete_preset_as_json_without_api_client(self, tmp_path, capsys):
        preset = get_endpoint_preset()
        EndpointPresetStore(tmp_path / ".dstack" / "presets").save(preset)

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    ["endpoint", "preset", "get", preset.id, "--json"],
                    home_dir=tmp_path,
                )
                == 0
            )
            from_config.assert_not_called()

        data = json.loads(capsys.readouterr().out)
        assert data["id"] == preset.id
        assert data["created_at"] == preset.created_at.isoformat()
        assert data["context_length"] == 32768
        assert data["validations"][0]["benchmark"]["metrics"]["total_output_tokens"] == 2048

    @pytest.mark.parametrize(
        "args",
        [
            ["endpoint", "preset", "--json"],
            ["endpoint", "preset", "list", "--json"],
        ],
    )
    def test_lists_complete_presets_as_json(self, tmp_path, capsys, args):
        preset = get_endpoint_preset()
        EndpointPresetStore(tmp_path / ".dstack" / "presets").save(preset)

        assert run_dstack_cli(args, home_dir=tmp_path) == 0

        output = json.loads(capsys.readouterr().out)
        assert len(output["presets"]) == 1
        data = output["presets"][0]
        assert data["id"] == preset.id
        assert data["created_at"] == preset.created_at.isoformat()
        assert data["context_length"] == 32768
        assert data["validations"][0]["benchmark"]["metrics"]["total_output_tokens"] == 2048

    def test_deletes_preset_without_api_client(self, tmp_path):
        preset = get_endpoint_preset()
        store = EndpointPresetStore(tmp_path / ".dstack" / "presets")
        store.save(preset)
        store.save(preset.copy(update={"id": "01234567"}))

        with patch("dstack.api.Client.from_config") as from_config:
            assert (
                run_dstack_cli(
                    ["endpoint", "preset", "delete", "--model", preset.base, "-y"],
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
        preset = get_endpoint_preset()
        result = SimpleNamespace(
            preset=preset,
            path=tmp_path / "preset.yaml",
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

    @pytest.mark.parametrize(
        ("extra_args", "expected_preset"),
        [([], "file-preset"), (["--preset", "cli-preset"], "cli-preset")],
    )
    def test_apply_passes_selected_profile_and_preset(self, tmp_path, extra_args, expected_preset):
        (tmp_path / ".dstack").mkdir()
        (tmp_path / ".dstack" / "profiles.yml").write_text(
            "profiles:\n  - name: gpu\n    max_price: 0.5\n"
        )
        configuration_path = tmp_path / "endpoint.dstack.yml"
        configuration_path.write_text(
            "type: endpoint\nname: qwen\nmodel:\n  base: Qwen/Qwen3.5-27B\npreset: file-preset\n"
        )

        with (
            patch("dstack.api.Client.from_config"),
            patch("dstack._internal.cli.commands.endpoint.apply_endpoint_preset") as apply,
        ):
            args = [
                "endpoint",
                "preset",
                "apply",
                "-f",
                str(configuration_path),
                "--profile",
                "gpu",
                *extra_args,
            ]
            exit_code = run_dstack_cli(
                args,
                home_dir=tmp_path,
                repo_dir=tmp_path,
            )

        assert exit_code == 0
        assert apply.call_args.kwargs["profile_name"] == "gpu"
        assert apply.call_args.kwargs["preset_id"] == expected_preset
        assert apply.call_args.kwargs["configuration"].max_price == 0.5
