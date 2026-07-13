import asyncio
import json
from types import SimpleNamespace

import pytest

from dstack._internal.cli.services.endpoint_agent_runtime import (
    ClaudeAuth,
    EndpointAgentProcessOutput,
    EndpointAgentWorkspace,
)
from dstack._internal.cli.services.endpoint_preset_create import (
    _build_prompt,
    _cleanup_runs,
    _create_endpoint_preset,
    _get_build_name,
)
from dstack._internal.cli.services.endpoint_presets import EndpointPresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.runs import Run, RunStatus
from tests._internal.cli.endpoint_presets import (
    get_endpoint_benchmark,
    get_running_service_run,
    get_successful_endpoint_report,
)

pytestmark = pytest.mark.windows


def _claude_auth() -> ClaudeAuth:
    return ClaudeAuth(
        api_key="anthropic-secret",
        executable="claude",
        effort=None,
        model="claude-test",
        use_existing=False,
    )


@pytest.fixture
def creation_context(tmp_path, monkeypatch):
    run = get_running_service_run()
    run_apis = _FakeRunAPIs(run)
    api = SimpleNamespace(
        project="main",
        runs=run_apis,
        client=SimpleNamespace(
            _token="dstack-secret",
            base_url="http://127.0.0.1:3000",
            runs=run_apis,
        ),
    )
    configuration = EndpointConfiguration(
        name="qwen-build",
        model={"base": "Qwen/Qwen3.5-27B"},
        context_length=8192,
        fleets=["gpu-fleet"],
        env={"LICENSE": "license-secret"},
    )
    monkeypatch.setattr(
        "dstack._internal.cli.services.endpoint_preset_create.get_claude_auth",
        _claude_auth,
    )
    monkeypatch.setattr(
        "dstack._internal.cli.services.endpoint_preset_create._get_build_name",
        lambda _: "qwen-build",
    )
    return SimpleNamespace(
        api=api,
        configuration=configuration,
        run=run,
        run_apis=run_apis,
        store=EndpointPresetStore(tmp_path / "presets"),
    )


class TestCreateEndpointPreset:
    @pytest.mark.asyncio
    async def test_checks_active_fleets_before_claude_auth(self, tmp_path, monkeypatch):
        api = SimpleNamespace(
            project="main",
            client=SimpleNamespace(fleets=SimpleNamespace(list=lambda *args, **kwargs: [])),
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_preset_create.get_claude_auth",
            lambda: pytest.fail("Claude auth must not be checked without an active fleet"),
        )

        with pytest.raises(CLIError, match="no active fleets"):
            await _create_endpoint_preset(
                api=api,
                configuration=EndpointConfiguration(
                    name="qwen-build",
                    model={"base": "Qwen/Qwen3.5-27B"},
                ),
                store=EndpointPresetStore(tmp_path / "presets"),
            )

    @pytest.mark.asyncio
    async def test_cleans_up_runs_when_cancelled(self, creation_context, monkeypatch):
        async def run_agent(**_):
            raise asyncio.CancelledError

        cleanup_calls = []

        async def cleanup_runs(**kwargs):
            cleanup_calls.append(kwargs)

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_preset_create.run_endpoint_agent",
            run_agent,
        )
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_preset_create._cleanup_runs",
            cleanup_runs,
        )

        with pytest.raises(asyncio.CancelledError):
            await _create_endpoint_preset(
                api=creation_context.api,
                configuration=creation_context.configuration,
                store=creation_context.store,
            )

        assert len(cleanup_calls) == 1
        assert cleanup_calls[0]["build_name"] == "qwen-build"

    @pytest.mark.parametrize(
        ("keep_service", "stopped_names"),
        [(False, ["qwen-build-2"]), (True, [])],
    )
    @pytest.mark.asyncio
    async def test_saves_recipe_and_cleans_up_runs(
        self, creation_context, monkeypatch, keep_service, stopped_names
    ):
        async def run_agent(**kwargs):
            workspace = kwargs["workspace"]
            benchmark = get_endpoint_benchmark(
                run_id=creation_context.run.id,
                run_name=creation_context.run.run_spec.run_name,
            )
            workspace.benchmarks_path.write_text(benchmark.json() + "\n")
            return EndpointAgentProcessOutput(
                report_data=json.loads(get_successful_endpoint_report(creation_context.run).json())
            )

        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_preset_create.run_endpoint_agent",
            run_agent,
        )
        result = await _create_endpoint_preset(
            api=creation_context.api,
            configuration=creation_context.configuration,
            store=creation_context.store,
            keep_service=keep_service,
        )

        assert result.recipe.base == "Qwen/Qwen3.5-27B"
        assert result.path.is_file()
        assert creation_context.store.list() == [result.recipe]
        assert "license-secret" not in result.path.read_text()
        assert creation_context.run_apis.stopped_names == stopped_names


class TestBuildName:
    def test_requires_name_and_keeps_generated_prefix_bounded(self, monkeypatch):
        with pytest.raises(CLIError, match="Endpoint name is required"):
            _get_build_name(None)
        monkeypatch.setattr(
            "dstack._internal.cli.services.endpoint_preset_create.secrets.token_hex",
            lambda _: "a1b2c3",
        )

        build_name = _get_build_name("qwen-endpoint-with-a-name-that-is-forty-one")

        assert len(f"{build_name}-99999") <= 41


class TestBuildPrompt:
    def test_distinguishes_base_from_exact_model(self):
        base_prompt = _build_prompt(
            configuration=EndpointConfiguration(
                name="qwen",
                model={"base": "Qwen/Qwen3.5-27B"},
                context_length=8192,
            ),
            build_name="qwen-build",
            allowed_fleets=("gpu-fleet",),
        )
        exact_prompt = _build_prompt(
            configuration=EndpointConfiguration(
                name="qwen",
                model={
                    "repo": "community/Qwen3.5-27B-GPTQ-Int4",
                    "name": "Qwen/Qwen3.5-27B",
                },
            ),
            build_name="qwen-build",
            allowed_fleets=("gpu-fleet",),
        )

        assert "- base_model: Qwen/Qwen3.5-27B" in base_prompt
        assert "- model_repo:" not in base_prompt
        assert "- context_length: 8192" in base_prompt
        assert "- model_repo: community/Qwen3.5-27B-GPTQ-Int4" in exact_prompt
        assert "- base_model:" not in exact_prompt
        assert "- context_length:" not in exact_prompt


class TestCleanupRuns:
    @pytest.mark.asyncio
    async def test_stops_only_recorded_build_runs(self, tmp_path, monkeypatch):
        (tmp_path / "submissions.jsonl").write_text(
            '{"name":"qwen-build-1"}\n{"name":"unrelated-run"}\n{"name":"qwen-build-2"}\n'
        )
        runs = _FakeRuns()
        api = SimpleNamespace(
            runs=runs,
            project="main",
            client=SimpleNamespace(runs=runs),
        )

        async def no_sleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        await _cleanup_runs(
            api=api,
            build_name="qwen-build",
            workspace=EndpointAgentWorkspace(
                path=tmp_path,
                dstack_home=tmp_path / "home",
            ),
            final_run_name="qwen-build-2",
            keep_final_service=True,
        )

        assert runs.stopped_names == ["qwen-build-1"]


class _FakeRuns:
    def __init__(self):
        self.stopped_names: list[str] = []

    def get(self, name):
        status = RunStatus.TERMINATED if name in self.stopped_names else RunStatus.RUNNING
        return SimpleNamespace(status=status)

    def stop(self, project, names, abort):
        assert project == "main"
        assert abort is False
        self.stopped_names.extend(names)


class _FakeRunAPIs:
    def __init__(self, run: Run):
        self.run = run
        self.stopped_names: list[str] = []

    def get(self, *args):
        name = args[-1]
        return self.run if name == self.run.run_spec.run_name else None

    def stop(self, project, names, abort):
        assert project == "main"
        assert abort is False
        self.stopped_names.extend(names)
        self.run.status = RunStatus.TERMINATED
