import asyncio
import json
import secrets
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from dstack._internal.cli.services.endpoint_agent_runtime import (
    EndpointAgentWorkspace,
    build_endpoint_agent_env,
    contains_redacted_value,
    endpoint_agent_workspace,
    get_claude_auth,
    get_redacted_values,
    get_sensitive_inherited_env_values,
    print_endpoint_progress,
    run_endpoint_agent,
)
from dstack._internal.cli.services.endpoint_preset_verify import (
    build_verified_endpoint_preset,
    load_endpoint_agent_report,
    load_endpoint_benchmarks,
)
from dstack._internal.cli.services.endpoint_presets import EndpointPresetStore
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.endpoint_agent import AgentFinalReport
from dstack._internal.core.models.endpoint_presets import EndpointPresetRecipe
from dstack._internal.core.models.endpoints import EndpointConfiguration
from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.core.services.endpoint_agent import (
    format_endpoint_constraints,
    get_endpoint_agent_system_prompt,
)
from dstack._internal.core.services.endpoint_presets import endpoint_preset_recipe_to_data
from dstack.api import Client

_RUN_STOP_TIMEOUT_SECONDS = 10 * 60


@dataclass(frozen=True)
class EndpointPresetCreateResult:
    recipe: EndpointPresetRecipe
    path: Path
    final_run_id: uuid.UUID
    final_run_name: str


def create_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    store: EndpointPresetStore,
    keep_service: bool = False,
    build_name: Optional[str] = None,
) -> EndpointPresetCreateResult:
    return asyncio.run(
        _create_endpoint_preset(
            api=api,
            configuration=configuration,
            store=store,
            keep_service=keep_service,
            build_name=build_name,
        )
    )


async def _create_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    store: EndpointPresetStore,
    keep_service: bool = False,
    build_name: Optional[str] = None,
) -> EndpointPresetCreateResult:
    build_name = build_name or _get_build_name(configuration.name)
    allowed_fleets = _get_allowed_fleets(api, configuration)
    if not allowed_fleets:
        raise CLIError("The project has no active fleets available for preset creation")
    auth = get_claude_auth()

    endpoint_env = configuration.env.as_dict()
    token = getattr(api.client, "_token", None)
    if not isinstance(token, str) or not token:
        raise CLIError("The configured dstack client has no authentication token")
    redacted_values = get_redacted_values(
        [
            token,
            auth.api_key or "",
            *endpoint_env.values(),
            *get_sensitive_inherited_env_values(),
        ]
    )
    report: Optional[AgentFinalReport] = None
    recipe: Optional[EndpointPresetRecipe] = None
    preset_path: Optional[Path] = None
    creation_succeeded = False
    cleanup_error: Optional[str] = None
    with endpoint_agent_workspace() as workspace:
        env = build_endpoint_agent_env(
            api=api,
            endpoint_env=endpoint_env,
            auth=auth,
            workspace=workspace,
            token=token,
        )
        prompt = _build_prompt(
            configuration=configuration,
            build_name=build_name,
            allowed_fleets=allowed_fleets,
        )
        print_endpoint_progress(
            f"Starting endpoint preset creation for {configuration.model.api_model_name}. "
            f"Allowed fleets: {', '.join(allowed_fleets)}."
        )
        try:
            process_output = await run_endpoint_agent(
                prompt=prompt,
                env=env,
                workspace=workspace,
                auth=auth,
                redacted_values=redacted_values,
            )
            report = load_endpoint_agent_report(
                output=process_output,
                workspace=workspace,
                redacted_values=redacted_values,
            )
            benchmarks = load_endpoint_benchmarks(workspace, report=report)
            run = api.client.runs.get(api.project, report.run_name)
            recipe = build_verified_endpoint_preset(
                run=run,
                endpoint_configuration=configuration,
                report=report,
                benchmarks=benchmarks,
            )
            if contains_redacted_value(endpoint_preset_recipe_to_data(recipe), redacted_values):
                raise CLIError("Generated endpoint preset contains a secret value")
            preset_path = store.save(recipe)
            print_endpoint_progress(
                f"Saved endpoint preset recipe {recipe.id} for {recipe.base} at {preset_path}."
            )
            creation_succeeded = True
        finally:
            keep_final_service = keep_service and creation_succeeded
            try:
                await _cleanup_runs(
                    api=api,
                    build_name=build_name,
                    workspace=workspace,
                    final_run_name=report.run_name if report is not None else None,
                    keep_final_service=keep_final_service,
                )
            except Exception as e:
                cleanup_error = str(e)
                if keep_final_service:
                    with suppress(Exception):
                        await _cleanup_runs(
                            api=api,
                            build_name=build_name,
                            workspace=workspace,
                            final_run_name=report.run_name if report is not None else None,
                        )

    if cleanup_error is not None:
        raise CLIError(f"Failed to clean up preset creation runs: {cleanup_error}")
    assert recipe is not None
    assert preset_path is not None
    assert report is not None
    assert report.run_id is not None
    assert report.run_name is not None
    return EndpointPresetCreateResult(
        recipe=recipe,
        path=preset_path,
        final_run_id=report.run_id,
        final_run_name=report.run_name,
    )


def _get_build_name(endpoint_name: Optional[str]) -> str:
    if endpoint_name is None:
        raise CLIError("Endpoint name is required. Set `name` in the configuration or use --name")
    suffix = secrets.token_hex(3)
    # Leave room for the numeric submission suffix while retaining a recognizable prefix.
    prefix = endpoint_name[:28].rstrip("-")
    return f"{prefix}-{suffix}"


def _get_allowed_fleets(api: Client, configuration: EndpointConfiguration) -> tuple[str, ...]:
    if configuration.fleets is not None:
        return tuple(
            fleet.format() if hasattr(fleet, "format") else str(fleet)
            for fleet in configuration.fleets
        )
    fleets = api.client.fleets.list(api.project, include_imported=True)
    return tuple(
        fleet.name if fleet.project_name == api.project else f"{fleet.project_name}/{fleet.name}"
        for fleet in fleets
        if fleet.status == FleetStatus.ACTIVE
    )


def _build_prompt(
    *,
    configuration: EndpointConfiguration,
    build_name: str,
    allowed_fleets: Sequence[str],
) -> str:
    context_lines = [f"- service_model_name: {configuration.model.api_model_name}"]
    if configuration.model.allows_variant_selection:
        context_lines.append(f"- base_model: {configuration.model.api_model_name}")
    else:
        context_lines.append(f"- model_repo: {configuration.model.exact_repo}")
    if configuration.context_length is not None:
        context_lines.append(f"- context_length: {configuration.context_length}")
    return f"""{get_endpoint_agent_system_prompt()}

Endpoint context:
- endpoint_name: {build_name}
{chr(10).join(context_lines)}

{
        format_endpoint_constraints(
            configuration,
            configuration.env.as_dict(),
            allowed_fleets=allowed_fleets,
        )
    }
"""


async def _cleanup_runs(
    *,
    api: Client,
    build_name: str,
    workspace: EndpointAgentWorkspace,
    final_run_name: Optional[str],
    keep_final_service: bool = False,
) -> None:
    run_names = _load_submitted_run_names(workspace.submissions_path)
    if final_run_name is not None:
        run_names.append(final_run_name)
    run_names = list(dict.fromkeys(run_names))
    expected_prefix = f"{build_name}-"
    run_names = [name for name in run_names if name.startswith(expected_prefix)]
    if keep_final_service:
        run_names = [name for name in run_names if name != final_run_name]
    active_names = []
    for name in run_names:
        run = api.runs.get(name)
        if run is not None and not run.status.is_finished():
            active_names.append(name)
    if not active_names:
        return
    print_endpoint_progress(f"Stopping preset creation runs: {', '.join(active_names)}.")
    api.client.runs.stop(api.project, active_names, abort=False)
    deadline = asyncio.get_running_loop().time() + _RUN_STOP_TIMEOUT_SECONDS
    pending = set(active_names)
    while pending:
        if asyncio.get_running_loop().time() >= deadline:
            raise CLIError(f"Timed out waiting for runs to stop: {', '.join(sorted(pending))}")
        for name in list(pending):
            run = api.runs.get(name)
            if run is None or run.status.is_finished():
                pending.remove(name)
        if pending:
            await asyncio.sleep(2)
    print_endpoint_progress("All preset creation runs stopped.")


def _load_submitted_run_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            name = value["name"].strip()
            if name:
                names.append(name)
    return names
