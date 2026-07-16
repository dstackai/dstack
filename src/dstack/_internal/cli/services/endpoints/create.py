import asyncio
import json
import os
import secrets
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from dstack._internal.cli.models.endpoint_agent import AgentFinalReport
from dstack._internal.cli.models.endpoint_presets import EndpointPreset
from dstack._internal.cli.models.endpoints import EndpointConfiguration
from dstack._internal.cli.services.endpoints.agent import (
    EndpointAgentSession,
    EndpointAgentWorkspace,
    build_endpoint_agent_env,
    contains_redacted_value,
    create_endpoint_agent_session,
    endpoint_agent_workspace,
    get_claude_auth,
    get_redacted_values,
    get_sensitive_inherited_env_values,
    print_endpoint_progress,
    run_endpoint_agent,
)
from dstack._internal.cli.services.endpoints.presets import endpoint_preset_to_data
from dstack._internal.cli.services.endpoints.prompt import (
    format_endpoint_constraints,
    get_endpoint_agent_system_prompt,
)
from dstack._internal.cli.services.endpoints.store import EndpointPresetStore
from dstack._internal.cli.services.endpoints.verify import (
    build_verified_endpoint_preset,
    load_endpoint_agent_report,
)
from dstack._internal.cli.utils.common import console, warn
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.envs import EnvSentinel
from dstack._internal.core.models.fleets import FleetStatus
from dstack.api import Client

_RUN_STOP_TIMEOUT_SECONDS = 10 * 60


@dataclass(frozen=True)
class EndpointPresetCreateResult:
    preset: EndpointPreset
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
    debug: bool = False,
) -> EndpointPresetCreateResult:
    agent_session = create_endpoint_agent_session(configuration, debug=debug)
    try:
        resolved_configuration = _resolve_endpoint_env(configuration)
        result = asyncio.run(
            _create_endpoint_preset(
                api=api,
                configuration=resolved_configuration,
                source_configuration=configuration,
                store=store,
                keep_service=keep_service,
                build_name=build_name,
                agent_session=agent_session,
            )
        )
    except BaseException:
        _finish_agent_session(agent_session)
        raise
    _finish_agent_session(agent_session, result.preset.id)
    return result


async def _create_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    store: EndpointPresetStore,
    source_configuration: Optional[EndpointConfiguration] = None,
    keep_service: bool = False,
    build_name: Optional[str] = None,
    agent_session: EndpointAgentSession,
) -> EndpointPresetCreateResult:
    source_configuration = source_configuration or configuration
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
    preset: Optional[EndpointPreset] = None
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
        if agent_session.debug:
            agent_session.write_prompt(prompt)
        print_endpoint_progress(
            f"Starting endpoint preset creation for {configuration.model.api_model_name}. "
            f"Allowed fleets: {', '.join(allowed_fleets)}.",
            agent_session=agent_session,
        )
        try:
            process_output = await run_endpoint_agent(
                prompt=prompt,
                env=env,
                workspace=workspace,
                auth=auth,
                redacted_values=redacted_values,
                agent_session=agent_session,
            )
            report = load_endpoint_agent_report(
                output=process_output,
                workspace=workspace,
                redacted_values=redacted_values,
            )
            run = api.client.runs.get(api.project, report.run_name)
            preset = build_verified_endpoint_preset(
                run=run,
                endpoint_configuration=source_configuration,
                report=report,
            )
            if contains_redacted_value(endpoint_preset_to_data(preset), redacted_values):
                raise CLIError("Generated endpoint preset contains a secret value")
            preset_path = store.save(preset)
            print_endpoint_progress(
                f"Saved endpoint preset {preset.id} for {preset.base} at {preset_path}.",
                agent_session=agent_session,
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
                    agent_session=agent_session,
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
                            agent_session=agent_session,
                        )

    if cleanup_error is not None:
        raise CLIError(f"Failed to clean up preset creation runs: {cleanup_error}")
    assert preset is not None
    assert preset_path is not None
    assert report is not None
    assert report.run_id is not None
    assert report.run_name is not None
    return EndpointPresetCreateResult(
        preset=preset,
        path=preset_path,
        final_run_id=report.run_id,
        final_run_name=report.run_name,
    )


def _resolve_endpoint_env(configuration: EndpointConfiguration) -> EndpointConfiguration:
    configuration = configuration.copy(deep=True)
    for key, value in configuration.env.items():
        if not isinstance(value, EnvSentinel):
            continue
        try:
            configuration.env[key] = value.from_env(os.environ)
        except ValueError as e:
            raise ConfigurationError(str(e)) from e
    return configuration


def _finish_agent_session(
    session: EndpointAgentSession,
    preset_id: Optional[str] = None,
) -> None:
    try:
        path = session.finish(preset_id)
    except OSError as e:
        path = session.path
        warn(f"Could not finalize agent output. Files remain at {path}: {e}")
    console.print(f"Agent log saved to [code]{path / 'agent.log'}[/]")


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
    agent_session: EndpointAgentSession,
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
    print_endpoint_progress(
        f"Stopping preset creation runs: {', '.join(active_names)}.",
        agent_session=agent_session,
    )
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
    print_endpoint_progress("All preset creation runs stopped.", agent_session=agent_session)


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
