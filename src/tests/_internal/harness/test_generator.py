import argparse

import pytest
import yaml

from dstack._internal.cli.services.args import gpu_spec
from dstack._internal.core.errors import CLIError
from dstack._internal.harness.generator import (
    _extract_yaml,
    generate_service_configuration,
    parse_service_yaml,
    regenerate_service_configuration,
    save_service_configuration,
)
from dstack._internal.harness.models import EndpointCreateParams, default_endpoint_name


class _StubLLM:
    def __init__(self, response: str):
        self.response = response
        self.last_system_prompt = None
        self.last_user_prompt = None

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_prompt = user_prompt
        return self.response


class TestDefaultEndpointName:
    def test_derives_stable_name_from_model(self):
        assert (
            default_endpoint_name("meta-llama/Meta-Llama-3.1-8B-Instruct")
            == "meta-llama-3-1-8b-instruct"
        )

    def test_handles_model_without_org(self):
        assert default_endpoint_name("gpt-4o") == "gpt-4o"


class TestEndpointCreateParams:
    def test_from_namespace_includes_cli_options(self):
        args = argparse.Namespace(
            run_name=None,
            gpu_spec=gpu_spec("24GB"),
            cpu_spec=None,
            memory_spec=None,
            disk_spec=None,
            backends=["runpod"],
            regions=["us-east-1"],
            instance_types=None,
            fleets=None,
            max_price=None,
            max_duration=None,
            spot_policy=None,
            env_vars=[],
        )
        params = EndpointCreateParams.from_namespace(
            args, model="meta-llama/Meta-Llama-3.1-8B-Instruct"
        )
        assert params.gpu is not None
        assert params.backends == ["runpod"]
        assert params.regions == ["us-east-1"]
        assert params.name == "meta-llama-3-1-8b-instruct"
        assert "gpu" in params.cli_options()
        assert "backends" in params.cli_options()

    def test_apply_resources_args_overrides_llm_gpu(self):
        from dstack._internal.cli.services.resources import apply_resources_args

        yaml_text = """
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
commands:
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
resources:
  gpu: 80GB
"""
        configuration = parse_service_yaml(yaml_text)
        args = argparse.Namespace(
            cpu_spec=None,
            gpu_spec=gpu_spec("24GB"),
            memory_spec=None,
            disk_spec=None,
        )
        apply_resources_args(args, configuration)
        assert configuration.resources.gpu.memory.min == 24.0
        assert configuration.resources.gpu.memory.max == 24.0


class TestExtractYaml:
    def test_extracts_fenced_yaml(self):
        text = """Here is the config:
```yaml
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
commands:
  - uv pip install vllm
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
resources:
  gpu: 80GB
```
"""
        yaml_text = _extract_yaml(text)
        assert yaml_text.startswith("type: service")

    def test_raises_when_yaml_missing(self):
        with pytest.raises(CLIError):
            _extract_yaml("no yaml here")


class TestParseServiceYaml:
    def test_parses_valid_service_yaml(self):
        yaml_text = """
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
commands:
  - uv pip install vllm
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
resources:
  gpu: 80GB
"""
        configuration = parse_service_yaml(yaml_text)
        assert configuration.name == "llama"
        assert configuration.model.name == "meta-llama/Meta-Llama-3.1-8B-Instruct"

    def test_strips_secret_values_from_env(self):
        yaml_text = """
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
env:
  - HF_TOKEN=secret
commands:
  - echo hi
resources:
  gpu: 80GB
"""
        configuration = parse_service_yaml(yaml_text)
        assert "HF_TOKEN" in configuration.env
        assert configuration.env["HF_TOKEN"].key == "HF_TOKEN"


class TestSaveServiceConfiguration:
    def test_saves_yaml_with_python_version(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        yaml_text = """
type: service
name: llama
python: "3.12"
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
commands:
  - uv pip install vllm
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
resources:
  gpu: 80GB
"""
        configuration = parse_service_yaml(yaml_text)

        config_path = save_service_configuration(configuration)

        assert config_path.exists()
        saved = yaml.safe_load(config_path.read_text())
        assert saved["type"] == "service"
        assert saved["python"] == "3.12"
        # Re-parsing the saved file should succeed.
        parse_service_yaml(config_path.read_text())

    def test_never_persists_resolved_secret_values(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        yaml_text = """
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
env:
  - HF_TOKEN
commands:
  - echo hi
resources:
  gpu: 80GB
"""
        configuration = parse_service_yaml(yaml_text)
        # Simulate env resolution that happens via configurator.apply_args:
        # the sentinel is replaced by a real secret value in memory.
        configuration.env["HF_TOKEN"] = "hf_super_secret_value"

        config_path = save_service_configuration(configuration)

        content = config_path.read_text()
        assert "hf_super_secret_value" not in content
        saved = yaml.safe_load(content)
        assert saved["env"] == ["HF_TOKEN"]


class TestRegenerateServiceConfiguration:
    def test_uses_error_logs_and_returns_fixed_config(self, tmp_path):
        skill = tmp_path / "SKILL.md"
        skill.write_text("dummy skill")
        fixed_yaml = """```yaml
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
commands:
  - uv pip install vllm
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct --max-model-len 8192
resources:
  gpu: L4:1
```"""
        stub = _StubLLM(fixed_yaml)
        params = EndpointCreateParams(model="meta-llama/Meta-Llama-3.1-8B-Instruct", name="llama")

        configuration = regenerate_service_configuration(
            params=params,
            previous_yaml="type: service\nname: llama\n",
            error_logs="ValueError: 16.0 GiB KV cache is needed ... available 5.58 GiB",
            skill_path=str(skill),
            llm_client=stub,
        )

        assert "--max-model-len 8192" in configuration.commands[-1]
        assert "KV cache" in stub.last_user_prompt
        assert configuration.name == "llama"

    def test_generate_uses_stub_client(self, tmp_path):
        skill = tmp_path / "SKILL.md"
        skill.write_text("dummy skill")
        generated = """```yaml
type: service
name: llama
port: 8000
model: meta-llama/Meta-Llama-3.1-8B-Instruct
commands:
  - uv run vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
resources:
  gpu: L4:1
```"""
        stub = _StubLLM(generated)
        params = EndpointCreateParams(model="meta-llama/Meta-Llama-3.1-8B-Instruct", name="llama")

        configuration = generate_service_configuration(
            params=params, skill_path=str(skill), llm_client=stub
        )
        assert configuration.name == "llama"
