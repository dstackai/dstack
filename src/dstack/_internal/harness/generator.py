import json
import re
from pathlib import Path
from typing import Optional

import yaml

from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.configurations import (
    ApplyConfigurationType,
    ServiceConfiguration,
    parse_apply_configuration,
)
from dstack._internal.core.models.envs import Env
from dstack._internal.harness.llm import HarnessLLMClient
from dstack._internal.harness.models import EndpointCreateParams
from dstack._internal.harness.skill import load_skill_content

HARNESS_CONFIGS_DIR = Path(".dstack-harness-configs")

SYSTEM_PROMPT_PREFIX = """\
You generate dstack service configuration files for model inference endpoints.

Rules:
- Output a single valid YAML document for `type: service`
- Do not wrap the YAML in markdown unless you also include the YAML body in a fenced block
- Use only documented dstack service fields
- Put secret values only as env var names in `env`, never inline values
- Include `model`, `port`, `commands`, and `resources.gpu` when possible
- Prefer `python: "3.12"` unless the user requests a custom image
- User-provided CLI options in the request are mandatory: use the exact GPU, backends,
  regions, fleets, CPU, memory, disk, and other resource/profile values given
- Do not substitute different resource sizes or backends than those specified by the user
- Do not invent unsupported CLI flags or YAML properties

Reference skill:

"""

FIX_SYSTEM_PROMPT_PREFIX = """\
You fix dstack service configurations that failed to start on the GPU instance.

You are given the previous configuration and the container error logs. Return a
corrected single YAML document for `type: service`.

Rules:
- Change as little as possible to address the specific error in the logs
- Keep `model`, `name`, and `resources` unless the error requires changing them
- For vLLM KV-cache / out-of-memory errors, prefer adding serve flags such as
  `--max-model-len` or `--gpu-memory-utilization` rather than changing the GPU
- Keep secret values as env var names only, never inline values
- Use only documented dstack fields and valid serving CLI flags
- Do not invent unsupported CLI flags or YAML properties

Reference skill:

"""


def _extract_yaml(text: str) -> str:
    fenced = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    stripped = text.strip()
    if stripped.startswith("type:") or stripped.startswith("name:"):
        return stripped

    raise CLIError("Harness LLM response did not contain YAML configuration")


def _normalize_env_names(configuration: ServiceConfiguration) -> None:
    configuration.env = Env.parse_obj(list(configuration.env))


def _validate_service_configuration(configuration: ServiceConfiguration) -> ServiceConfiguration:
    if configuration.type != ApplyConfigurationType.SERVICE.value:
        raise CLIError("Generated configuration must have [code]type: service[/]")
    if configuration.model is None:
        raise CLIError("Generated configuration must include a [code]model[/] field")
    _normalize_env_names(configuration)
    return configuration


def parse_service_yaml(yaml_text: str) -> ServiceConfiguration:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise CLIError(f"Generated YAML is invalid: {e}") from e
    if not isinstance(data, dict):
        raise CLIError("Generated YAML must be a mapping")

    try:
        configuration = parse_apply_configuration(data)
    except ConfigurationError as e:
        raise CLIError(f"Generated configuration is invalid: {e}") from e

    if not isinstance(configuration, ServiceConfiguration):
        raise CLIError("Generated configuration must be a service configuration")
    return _validate_service_configuration(configuration)


def build_user_prompt(params: EndpointCreateParams) -> str:
    return (
        "Generate a dstack service configuration for an inference endpoint.\n"
        "The user passed these CLI options. You MUST use them exactly in the YAML."
        " Do not substitute different GPU memory, backends, regions, fleets,"
        " or other resource/profile values.\n"
        f"{json.dumps(params.cli_options(), indent=2, default=str)}\n\n"
        "Return only the YAML configuration."
    )


def build_fix_prompt(params: EndpointCreateParams, previous_yaml: str, error_logs: str) -> str:
    return (
        "The following dstack service configuration failed to start:\n"
        f"```yaml\n{previous_yaml}\n```\n\n"
        "Container error logs (tail):\n"
        f"```\n{error_logs}\n```\n\n"
        "Return only the corrected YAML configuration."
    )


def _apply_param_overrides(
    configuration: ServiceConfiguration, params: EndpointCreateParams
) -> None:
    if params.name:
        configuration.name = params.name
    if params.model:
        configuration.model = params.model


def generate_service_configuration(
    params: EndpointCreateParams,
    skill_path: Optional[str] = None,
    llm_client: Optional[HarnessLLMClient] = None,
) -> ServiceConfiguration:
    skill_content = load_skill_content(skill_path)
    client = llm_client or HarnessLLMClient()
    response = client.chat(
        system_prompt=SYSTEM_PROMPT_PREFIX + skill_content,
        user_prompt=build_user_prompt(params),
    )
    configuration = parse_service_yaml(_extract_yaml(response))
    _apply_param_overrides(configuration, params)
    return configuration


def regenerate_service_configuration(
    params: EndpointCreateParams,
    previous_yaml: str,
    error_logs: str,
    skill_path: Optional[str] = None,
    llm_client: Optional[HarnessLLMClient] = None,
) -> ServiceConfiguration:
    skill_content = load_skill_content(skill_path)
    client = llm_client or HarnessLLMClient()
    response = client.chat(
        system_prompt=FIX_SYSTEM_PROMPT_PREFIX + skill_content,
        user_prompt=build_fix_prompt(params, previous_yaml, error_logs),
    )
    configuration = parse_service_yaml(_extract_yaml(response))
    _apply_param_overrides(configuration, params)
    return configuration


def get_endpoint_path(name: str) -> Path:
    HARNESS_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    return HARNESS_CONFIGS_DIR / f"{name}.dstack.yml"


def save_service_configuration(configuration: ServiceConfiguration) -> Path:
    if not configuration.name:
        raise CLIError("Generated configuration must include a [code]name[/]")

    config_path = get_endpoint_path(configuration.name)
    # Round-trip through JSON so enums and other rich types become plain
    # primitives that yaml.safe_dump can represent.
    config_dict = json.loads(configuration.json(exclude_none=True))
    # Never persist secret values to disk: env is always written as names only,
    # even if values were resolved from the environment earlier in the flow.
    env_names = list(configuration.env)
    if env_names:
        config_dict["env"] = env_names
    else:
        config_dict.pop("env", None)
    config_path.write_text(
        yaml.safe_dump(config_dict, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
