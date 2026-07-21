import asyncio
import dataclasses
import json
import os
import re
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import yaml
from rich.table import Table

from dstack._internal.cli.models.endpoint_agent import AgentFinalReport
from dstack._internal.cli.models.endpoint_presets import EndpointPreset
from dstack._internal.cli.models.endpoints import (
    EndpointConfiguration,
    EndpointPresetConstraints,
)
from dstack._internal.cli.services.endpoints.agent import (
    EndpointAgentSession,
    EndpointAgentWorkspace,
    attach_agent_workspace,
    attach_endpoint_agent,
    build_endpoint_agent_env,
    claimed_session_name,
    contains_redacted_value,
    create_agent_workspace,
    create_endpoint_agent_session,
    get_claude_auth,
    get_redacted_values,
    get_sensitive_inherited_env_values,
    load_attachable_agent_session,
    print_endpoint_progress,
    redact,
    remove_agent_workspace,
    run_endpoint_agent,
    session_process_alive,
    terminate_agent_process,
)
from dstack._internal.cli.services.endpoints.presets import endpoint_preset_to_data
from dstack._internal.cli.services.endpoints.prompt import get_endpoint_agent_system_prompt
from dstack._internal.cli.services.endpoints.store import EndpointPresetStore
from dstack._internal.cli.services.endpoints.verify import (
    build_verified_endpoint_preset,
    load_endpoint_agent_report,
)
from dstack._internal.cli.utils.common import confirm_ask, console, warn
from dstack._internal.cli.utils.run import print_offers
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.envs import Env, EnvSentinel
from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.core.models.runs import RunSpec
from dstack.api import Client

_RUN_STOP_TIMEOUT_SECONDS = 10 * 60


@dataclass(frozen=True)
class EndpointPresetCreateResult:
    preset: EndpointPreset
    path: Path
    final_run_id: uuid.UUID
    final_run_name: str


class AgentExitedWithoutReport(Exception):
    """A detached agent died without submitting a report; the session is
    resumable rather than failed."""

    def __init__(self, error: Optional[str]) -> None:
        super().__init__(error or "The agent exited without a report")
        self.error = error


def attach_endpoint_preset(
    *,
    api: Client,
    store: EndpointPresetStore,
    preset_id: str,
    keep_service: bool = False,
) -> EndpointPresetCreateResult:
    agent_session = load_attachable_agent_session(preset_id)
    configuration_path = agent_session.path / "preset.dstack.yml"
    if not configuration_path.is_file():
        raise CLIError(
            f"Session {preset_id} has no configuration copy and cannot be attached;"
            f" resume it with [code]--resume {preset_id}[/] instead"
        )
    # The session copy is canonical output, not user input: parse it without
    # the user-facing deprecation warnings.
    try:
        configuration = EndpointConfiguration.parse_obj(
            yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError) as e:
        raise CLIError(f"Could not read the session configuration: {e}") from e
    try:
        result = asyncio.run(
            _create_endpoint_preset(
                api=api,
                configuration=_resolve_endpoint_env_best_effort(configuration),
                source_configuration=configuration,
                store=store,
                keep_service=keep_service,
                agent_session=agent_session,
                attach=True,
            )
        )
    except KeyboardInterrupt:
        _stop_or_detach_agent_session(agent_session, api)
        raise
    except AgentExitedWithoutReport as e:
        runs_stopped = _stop_active_session_runs(api, agent_session, assume_yes=False)
        _suspend_agent_session(agent_session, runs_left_active=not runs_stopped)
        raise CLIError(str(e)) from e
    except BaseException:
        _finish_agent_session(agent_session, "failed")
        remove_agent_workspace(agent_session)
        raise
    _finish_agent_session(agent_session, "success")
    remove_agent_workspace(agent_session)
    return result


def stop_endpoint_session(api: Client, preset_id: str, *, assume_yes: bool = False) -> None:
    session = load_attachable_agent_session(preset_id)
    terminate_agent_process(session.read_manifest())
    runs_stopped = _stop_active_session_runs(api, session, assume_yes=assume_yes)
    _suspend_agent_session(session, runs_left_active=not runs_stopped)


def _stop_active_session_runs(
    api: Client, session: EndpointAgentSession, *, assume_yes: bool
) -> bool:
    """Offers to stop the session's non-terminal runs; returns whether none
    are left active."""
    try:
        lines = session.runs_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    names = []
    for line in lines:
        try:
            name = json.loads(line).get("name")
        except json.JSONDecodeError:
            continue
        if isinstance(name, str) and name:
            names.append(name)
    active = []
    for name in names:
        try:
            run = api.client.runs.get(api.project, name)
        except Exception:  # noqa: BLE001
            continue
        if not run.status.is_finished():
            active.append(name)
    if not active:
        return True
    plural = "s" if len(active) != 1 else ""
    if not assume_yes and not confirm_ask(
        f"Stop {len(active)} active preset creation run{plural} ([code]{', '.join(active)}[/])?"
    ):
        return False
    with console.status("Stopping runs..."):
        api.client.runs.stop(api.project, active, abort=False)
    return True


def _resolve_endpoint_env_best_effort(
    configuration: EndpointConfiguration,
) -> EndpointConfiguration:
    """For attach: env values only feed redaction, and the agent already runs,
    so missing variables are tolerable."""
    configuration = configuration.copy(deep=True)
    kept: dict[str, str] = {}
    for key, value in configuration.env.items():
        if isinstance(value, EnvSentinel):
            resolved = os.environ.get(key)
            if resolved:
                kept[key] = resolved
        else:
            kept[key] = value
    configuration.env = Env.parse_obj(kept)
    return configuration


def create_endpoint_preset(
    *,
    api: Client,
    configuration: EndpointConfiguration,
    store: EndpointPresetStore,
    keep_service: bool = False,
    build_name: Optional[str] = None,
    debug: bool = False,
    resume_session: Optional[EndpointAgentSession] = None,
    user_prompt: Optional[str] = None,
    allowed_fleets: Optional[tuple[str, ...]] = None,
) -> EndpointPresetCreateResult:
    agent_session = resume_session or create_endpoint_agent_session(configuration, debug=debug)
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
                resume=resume_session is not None,
                user_prompt=user_prompt,
                allowed_fleets=allowed_fleets,
            )
        )
    except KeyboardInterrupt:
        _stop_or_detach_agent_session(agent_session, api)
        raise
    except BaseException:
        _finish_agent_session(agent_session, "failed")
        remove_agent_workspace(agent_session)
        raise
    _finish_agent_session(agent_session, "success")
    remove_agent_workspace(agent_session)
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
    resume: bool = False,
    attach: bool = False,
    user_prompt: Optional[str] = None,
    allowed_fleets: Optional[tuple[str, ...]] = None,
) -> EndpointPresetCreateResult:
    source_configuration = source_configuration or configuration
    initial_resume_session_id: Optional[str] = None
    if attach:
        auth = None
        workspace = attach_agent_workspace(agent_session)
        build_name = build_name or _load_build_name(workspace)
        allowed_fleets = ()
    elif resume:
        # The prompt is fixed at session creation, like the constraints.
        pinned_prompt = agent_session.read_user_prompt()
        if user_prompt is not None and user_prompt != pinned_prompt:
            warn(
                "The configuration prompt is ignored when resuming: the session keeps its original prompt"
            )
        user_prompt = pinned_prompt
        auth = get_claude_auth()
        workspace = attach_agent_workspace(agent_session)
        manifest = agent_session.read_manifest()
        claude_model = manifest.get("claude_model")
        if isinstance(claude_model, str) and claude_model:
            auth = dataclasses.replace(auth, model=claude_model)
        claude_session_id = manifest.get("claude_session_id")
        if isinstance(claude_session_id, str) and claude_session_id:
            initial_resume_session_id = claude_session_id
        build_name = build_name or _load_build_name(workspace)
        allowed_fleets = ()
    else:
        if allowed_fleets is None:
            allowed_fleets = _get_allowed_fleets(api, configuration)
        if not allowed_fleets:
            raise CLIError("The project has no active fleets available for preset creation")
        auth = get_claude_auth()
        workspace = create_agent_workspace(agent_session)
        build_name = build_name or _get_build_name(
            configuration.name, configuration.model.api_model_name, agent_session.preset_id
        )
    if auth is not None:
        agent_session.update_manifest(status="running", pid=os.getpid(), claude_model=auth.model)
    else:
        agent_session.update_manifest(status="running", pid=os.getpid())

    endpoint_env = configuration.env.as_dict()
    token = getattr(api.client, "_token", None)
    if not isinstance(token, str) or not token:
        raise CLIError("The configured dstack client has no authentication token")
    redacted_values = get_redacted_values(
        [
            token,
            (auth.api_key if auth is not None else None) or "",
            *endpoint_env.values(),
            *get_sensitive_inherited_env_values(),
        ]
    )
    env: dict[str, str] = {}
    report: Optional[AgentFinalReport] = None
    preset: Optional[EndpointPreset] = None
    preset_path: Optional[Path] = None
    creation_succeeded = False
    interrupted = False
    cleanup_error: Optional[str] = None
    if auth is not None:
        env = build_endpoint_agent_env(
            api=api,
            endpoint_env=endpoint_env,
            auth=auth,
            workspace=workspace,
            token=token,
        )
    prompt = get_endpoint_agent_system_prompt(user_prompt=user_prompt)
    if not resume and not attach:
        if user_prompt:
            agent_session.write_user_prompt(user_prompt)
        constraints_text = _build_constraints(
            configuration=configuration,
            build_name=build_name,
            allowed_fleets=allowed_fleets,
        )
        workspace.constraints_path.write_text(constraints_text, encoding="utf-8")
        if agent_session.debug:
            agent_session.write_prompt(prompt)
            agent_session.write_constraints(constraints_text)
            if auth is not None:
                agent_session.write_agent_info(auth)
    try:
        if attach:
            process_output = await attach_endpoint_agent(
                workspace=workspace,
                redacted_values=redacted_values,
                agent_session=agent_session,
            )
            if process_output.report_data is None and not workspace.final_report_path.exists():
                raise AgentExitedWithoutReport(process_output.error)
        else:
            assert auth is not None
            process_output = await run_endpoint_agent(
                prompt=prompt,
                env=env,
                workspace=workspace,
                auth=auth,
                redacted_values=redacted_values,
                agent_session=agent_session,
                initial_resume_session_id=initial_resume_session_id,
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
            preset_id=agent_session.preset_id or None,
            name=claimed_session_name(agent_session.read_manifest()),
        )
        if contains_redacted_value(endpoint_preset_to_data(preset), redacted_values):
            raise CLIError("Generated preset contains a secret value")
        preset_path = store.save(preset)
        print_endpoint_progress(
            f"Saved preset {preset.id} for {preset.base} at {preset_path}.",
            agent_session=agent_session,
        )
        creation_succeeded = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        interrupted = True
        raise
    finally:
        if agent_session.debug:
            _save_final_report_copy(
                workspace=workspace,
                agent_session=agent_session,
                redacted_values=redacted_values,
            )
        if not interrupted:
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
    status: str,
) -> None:
    try:
        path = session.finish(status)
    except OSError as e:
        path = session.path
        warn(f"Could not finalize agent output. Files remain at {path}: {e}")
    console.print(f"Agent log saved to [code]{path / 'agent.log'}[/]")


def _stop_or_detach_agent_session(
    session: EndpointAgentSession, api: Optional[Client] = None
) -> None:
    """Apply-style interrupt: stop the session, or detach and leave the agent
    working — it stays visible as a running session in `dstack preset`."""
    manifest = session.read_manifest()
    agent_alive = session_process_alive({**manifest, "pid": None})
    stop = True
    if agent_alive:
        try:
            stop = confirm_ask(f"Stop the preset creation session [code]{session.preset_id}[/]?")
        except (KeyboardInterrupt, EOFError):
            stop = True
    if stop:
        terminate_agent_process(manifest)
        runs_stopped = False
        if api is not None:
            runs_stopped = _stop_active_session_runs(api, session, assume_yes=False)
        _suspend_agent_session(session, runs_left_active=not runs_stopped)
        return
    session.update_manifest(pid=None)
    console.print(
        f"\nDetached. The session keeps running; attach with"
        f" [code]dstack preset attach {session.preset_id}[/]"
        f" or stop it with [code]dstack preset stop {session.preset_id}[/]."
    )


def _suspend_agent_session(
    session: EndpointAgentSession, *, runs_left_active: bool = True
) -> None:
    try:
        session.finish("interrupted")
    except OSError as e:
        warn(f"Could not record the interrupted session state: {e}")
    if runs_left_active:
        console.print(
            f"\nSession [code]{session.preset_id}[/] interrupted. "
            "Its runs may still be active and accruing cost."
        )
        console.print(
            f"Resume with [code]dstack preset create -f <configuration> "
            f"--resume {session.preset_id}[/], or stop the runs with [code]dstack stop[/]."
        )
    else:
        console.print(f"\nSession [code]{session.preset_id}[/] interrupted.")
        console.print(
            f"Resume with [code]dstack preset create -f <configuration> "
            f"--resume {session.preset_id}[/]."
        )


def _get_build_name(name: Optional[str], model_name: str, suffix: str) -> str:
    base = name or _model_slug(model_name)
    # Leave room for the preset id and numeric submission suffix while retaining
    # a recognizable prefix.
    prefix = base[:26].rstrip("-")
    return f"{prefix}-{suffix}"


def _model_slug(model_name: str) -> str:
    """A run-name-safe slug for name-less presets, from the model's basename."""
    basename = model_name.rsplit("/", 1)[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", basename.lower()).strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"model-{slug}".strip("-")
    return slug


def _load_build_name(workspace: EndpointAgentWorkspace) -> str:
    try:
        data = json.loads(workspace.constraints_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CLIError(f"The session constraints cannot be read: {e}") from e
    prefix = data.get("run_name_prefix") if isinstance(data, dict) else None
    if not isinstance(prefix, str) or not prefix:
        raise CLIError("The session constraints do not contain a run name prefix")
    return prefix


def plan_endpoint_preset(*, api: Client, configuration: EndpointConfiguration) -> tuple[str, ...]:
    """Resolves the allowed fleets and shows what the agent will have to work
    with — Project, User, the effective fleets, and their offers. Agent-free."""
    allowed_fleets = _get_allowed_fleets(api, configuration)
    if not allowed_fleets:
        raise CLIError("The project has no active fleets available for preset creation")
    _print_fleet_offers(api, allowed_fleets)
    return allowed_fleets


def _print_fleet_offers(api: Client, allowed_fleets: tuple[str, ...]) -> None:
    try:
        # Image and user are set so the server neither defaults gpu.vendor to
        # nvidia nor pulls image config from a registry (as in `dstack offer`).
        offer_configuration = TaskConfiguration(commands=[":"], image="scratch", user="root")
        offer_configuration.fleets = list(allowed_fleets)
        run_spec = RunSpec(configuration=offer_configuration, profile=None)
        with console.status("Getting offers..."):
            run_plan = api.client.runs.get_plan(api.project, run_spec, max_offers=10)
        props = Table(box=None, show_header=False)
        props.add_column(no_wrap=True)
        props.add_column()
        props.add_row("[bold]Project[/bold]", run_plan.project_name)
        props.add_row("[bold]User[/bold]", run_plan.user)
        props.add_row("[bold]Fleets[/bold]", ", ".join(allowed_fleets))
        console.print(props)
        console.print()
        print_offers(run_plan.job_plans[0], dim_after_first=False)
    except Exception as e:  # noqa: BLE001
        warn(f"Could not list offers for the allowed fleets: {e}")


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


def _build_constraints(
    *,
    configuration: EndpointConfiguration,
    build_name: str,
    allowed_fleets: Sequence[str],
) -> str:
    constraints = EndpointPresetConstraints.parse_obj(
        {
            "run_name_prefix": build_name,
            "model": json.loads(configuration.model.json(exclude_none=True)),
            "context_length": configuration.context_length,
            "max_trials": configuration.effective_max_trials,
            "concurrency": configuration.effective_concurrency,
            "fleets": list(allowed_fleets),
            "env": list(configuration.env),
        }
    )
    # All fields are always present; unset optional constraints render as null.
    return json.dumps(json.loads(constraints.json()), indent=2) + "\n"


def _save_final_report_copy(
    *,
    workspace: EndpointAgentWorkspace,
    agent_session: EndpointAgentSession,
    redacted_values: Sequence[str],
) -> None:
    if not workspace.final_report_path.exists():
        return
    try:
        report_text = workspace.final_report_path.read_text(encoding="utf-8", errors="replace")
        agent_session.write_final_report(redact(report_text, redacted_values))
    except OSError as e:
        warn(f"Could not save a final report copy: {e}")


async def _cleanup_runs(
    *,
    api: Client,
    build_name: str,
    workspace: EndpointAgentWorkspace,
    final_run_name: Optional[str],
    agent_session: EndpointAgentSession,
    keep_final_service: bool = False,
) -> None:
    run_names = _load_submitted_run_names(workspace.runs_path)
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
    if agent_session.debug:
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
