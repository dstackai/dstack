import asyncio
import dataclasses
import json
import os
import re
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml
from rich.table import Table
from rich.text import Text

from dstack._internal.cli.models.configurations import (
    PresetConfiguration,
    PresetConstraints,
)
from dstack._internal.cli.models.preset_agent import AgentFinalReport
from dstack._internal.cli.models.presets import Preset
from dstack._internal.cli.services.presets.agent import (
    PresetAgentSession,
    PresetAgentWorkspace,
    SessionBusyError,
    attach_agent_workspace,
    attach_preset_agent,
    build_preset_agent_env,
    claimed_session_name,
    contains_redacted_value,
    create_agent_workspace,
    create_preset_agent_session,
    get_claude_auth,
    get_redacted_values,
    get_sensitive_inherited_env_values,
    iter_agent_sessions,
    load_agent_session,
    load_attachable_agent_session,
    mark_session_owner,
    print_preset_progress,
    print_session_log,
    redact,
    release_session_claim,
    remove_agent_workspace,
    run_preset_agent,
    scrub_workspace_token,
    session_process_alive,
    session_report_exists,
    terminate_agent_process,
    try_claim_session,
)
from dstack._internal.cli.services.presets.presets import preset_to_data
from dstack._internal.cli.services.presets.prompt import get_preset_agent_system_prompt
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.cli.services.presets.verify import (
    build_verified_preset,
    load_preset_agent_report,
)
from dstack._internal.cli.utils.common import NO_OFFERS_WARNING, confirm_ask, console, warn
from dstack._internal.cli.utils.offers import print_offers_table
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.envs import Env, EnvSentinel
from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.core.models.runs import RunSpec
from dstack.api import Client

_RUN_STOP_TIMEOUT_SECONDS = 10 * 60
_NO_FLEETS_ERROR = "The project has no fleets. Create one before creating a preset"


@dataclass(frozen=True)
class PresetCreateResult:
    preset: Preset
    path: Path
    final_run_id: uuid.UUID
    final_run_name: str


class AgentExitedWithoutReport(Exception):
    """A detached agent died without submitting a report; the session is
    resumable rather than failed."""

    def __init__(self, error: Optional[str]) -> None:
        super().__init__(error or "The agent exited without a report")
        self.error = error


def follow_preset(
    *,
    api: Client,
    store: PresetStore,
    preset_id: str,
    keep_service: bool = False,
    wait_for_run_stop: bool = True,
    echo: bool = True,
) -> PresetCreateResult:
    """Re-owns a detached session: follows its agent to completion, then
    verifies and saves the preset (the finalize role, which must run CLI-side
    for secret-scrubbing and server-verified preset building).

    Always takes the exclusive finalize lock so a concurrent `logs -f` and
    reconcile can't both finalize the same session. `wait_for_run_stop=False`
    and `echo=False` make it non-blocking and silent for reconcile."""
    agent_session = load_attachable_agent_session(preset_id)
    agent_session.echo = echo
    lock = try_claim_session(agent_session)
    if lock is None:
        raise SessionBusyError(f"Preset {preset_id} is being finalized by another process")
    try:
        configuration = _load_session_configuration(agent_session)
        try:
            result = asyncio.run(
                _create_preset(
                    api=api,
                    configuration=_resolve_preset_env(configuration, strict=False),
                    source_configuration=configuration,
                    store=store,
                    keep_service=keep_service,
                    agent_session=agent_session,
                    attach=True,
                    wait_for_run_stop=wait_for_run_stop,
                )
            )
        except KeyboardInterrupt:
            # `logs -f` is a viewer: Ctrl+C detaches and leaves the agent
            # running (reconcile finalizes it later), never stops it.
            _detach_agent_session(agent_session)
            raise
        except AgentExitedWithoutReport as e:
            _stop_active_session_runs(api, agent_session)
            _suspend_agent_session(agent_session)
            raise CLIError(str(e)) from e
        except CLIError:
            # Definitive: a failure/invalid report, an unverifiable service, or a
            # leaked secret — the preset genuinely cannot be built, so fail it.
            _close_agent_session(agent_session, "failed")
            raise
        # A transient error (network / OS) propagates untouched: the completed
        # session and its report stay intact for a later follow or reconcile.
        _close_agent_session(agent_session, "success")
        return result
    finally:
        release_session_claim(lock)


def _load_session_configuration(agent_session: PresetAgentSession) -> PresetConfiguration:
    configuration_path = agent_session.path / "preset.dstack.yml"
    if not configuration_path.is_file():
        raise CLIError(
            f"Preset {agent_session.preset_id} has no saved configuration and cannot be"
            f" followed; resume it with [code]--resume {agent_session.preset_id}[/] instead"
        )
    # The session copy is canonical output, not user input: parse it without
    # the user-facing deprecation warnings.
    try:
        return PresetConfiguration.parse_obj(
            yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError) as e:
        raise CLIError(f"Could not read the preset configuration: {e}") from e


def show_preset_session_logs(
    *,
    project: Optional[str],
    store: PresetStore,
    preset_id: str,
    follow: bool,
    keep_service: bool,
) -> Optional[PresetCreateResult]:
    """`logs`: dump a session's log (any status). With `follow`, a still-live
    session is re-owned, followed to completion, and its preset saved; a
    finished session just prints its log. Returns the saved preset, if any."""
    session = load_agent_session(preset_id)
    status = session.read_manifest().get("status")
    if not follow or status in ("success", "failed", "interrupted"):
        print_session_log(session)
        if follow and status == "interrupted":
            console.print(
                f"\nPreset [code]{preset_id}[/] creation was interrupted; resume it with"
                f" [code]dstack preset create -f <config> --resume {preset_id}[/]."
            )
        return None
    # Following a live session: print the log so far, then stream new progress
    # (a future --since could bound this). The client is built only here, so a
    # read-only dump never needs a server or authentication.
    print_session_log(session)
    try:
        return follow_preset(
            api=Client.from_config(project_name=project),
            store=store,
            preset_id=preset_id,
            keep_service=keep_service,
        )
    except SessionBusyError:
        # Another CLI already owns the finalize; follow read-only instead of
        # refusing, so any number of viewers can watch the same preset at once.
        _follow_session_log_readonly(session)
        return None


def _follow_session_log_readonly(session: PresetAgentSession) -> None:
    """Read-only follow: another CLI owns the finalize, so just stream the log it
    writes until the preset reaches a terminal state."""
    try:
        offset = session.log_path.stat().st_size
    except OSError:
        offset = 0
    while True:
        try:
            with session.log_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(offset)
                chunk = f.read()
                offset = f.tell()
        except OSError:
            chunk = ""
        if chunk:
            console.print(Text(chunk.rstrip("\n")), soft_wrap=True)
        manifest = session.read_manifest()
        if manifest.get("status") in ("success", "failed", "interrupted"):
            return
        if not chunk and not session_process_alive(manifest):
            # The owner died without recording a terminal status; stop tailing
            # rather than poll forever.
            console.print(
                f"The process creating preset [code]{session.preset_id}[/] exited;"
                f" follow it again with [code]dstack preset logs -f {session.preset_id}[/]"
            )
            return
        time.sleep(1)


def reconcile_detached_sessions(store: PresetStore) -> None:
    """Finalizes sessions whose agent completed while no CLI was attached
    (graceful detach, or an ungraceful CLI death). This is what makes the saved
    preset independent of a foreground process: any read command runs it, and
    the work materializes from the on-disk report.

    Best-effort and parallel-safe — finalize takes an exclusive claim, and every
    error is swallowed so the calling read command never fails.
    """
    for session in iter_agent_sessions():
        if _is_reconcilable(session.read_manifest()):
            _reconcile_session(session, store)


def _is_reconcilable(manifest: dict[str, Any]) -> bool:
    # An orphaned session (no live owner) whose agent left a completion report.
    # A session interrupted mid-work has no report and stays resumable; one
    # stopped *after* the agent finished is finalized by `stop` itself, not here.
    # Sessions created before finalize context was persisted lack `project` and
    # are skipped — they finalize interactively via `logs -f`.
    return (
        manifest.get("status") == "running"
        and bool(manifest.get("project"))
        and session_report_exists(manifest)
        and not session_process_alive(manifest)
    )


def _reconcile_session(session: PresetAgentSession, store: PresetStore) -> None:
    manifest = session.read_manifest()
    try:
        api = Client.from_config(project_name=str(manifest.get("project") or ""))
    except Exception:  # noqa: BLE001 — offline/misconfigured must not break the read command
        return
    # follow_preset takes the finalize claim (so a concurrent `logs -f`
    # or reconcile can't double-finalize), records the terminal status itself,
    # and leaves the session intact on a transient error. Every outcome is silent
    # here — the result shows in the list that follows.
    with suppress(Exception):
        follow_preset(
            api=api,
            store=store,
            preset_id=session.preset_id,
            keep_service=bool(manifest.get("keep_service")),
            wait_for_run_stop=False,
            echo=False,
        )


def stop_preset_session(api: Client, preset_id: str) -> None:
    session = load_attachable_agent_session(preset_id)
    manifest = session.read_manifest()
    # If the agent already finished, there is nothing to stop. Leave the session
    # for a read to save (reconcile-on-read) rather than discarding it as
    # interrupted — but `stop` itself never saves; it only stops.
    if session_report_exists(manifest) and not session_process_alive(manifest):
        console.print(f"Preset [code]{preset_id}[/] has already finished.")
        return
    terminate_agent_process(manifest)
    _stop_active_session_runs(api, session)
    _suspend_agent_session(session)


def _stop_active_session_runs(api: Client, session: PresetAgentSession) -> None:
    """Stops the session's non-terminal runs (with a spinner), like `dstack
    stop`. Keeping a trial instance warm for resume is the detach path, not this."""
    names = _load_submitted_run_names(session.runs_path)
    active = []
    for name in names:
        try:
            run = api.client.runs.get(api.project, name)
        except Exception:  # noqa: BLE001
            continue
        if not run.status.is_finished():
            active.append(name)
    if not active:
        return
    with console.status("Stopping runs..."):
        api.client.runs.stop(api.project, active, abort=False)


def _resolve_preset_env(
    configuration: PresetConfiguration, *, strict: bool = True
) -> PresetConfiguration:
    """Resolves `EnvSentinel` entries from the process environment. Non-strict
    drops unresolvable entries instead of raising — for attach, where env values
    only feed redaction and the agent already runs."""
    configuration = configuration.copy(deep=True)
    resolved: dict[str, str] = {}
    for key, value in configuration.env.items():
        if isinstance(value, EnvSentinel):
            try:
                resolved[key] = value.from_env(os.environ)
            except ValueError as e:
                if strict:
                    raise ConfigurationError(str(e)) from e
        else:
            resolved[key] = value
    configuration.env = Env.parse_obj(resolved)
    return configuration


def create_preset(
    *,
    api: Client,
    configuration: PresetConfiguration,
    store: PresetStore,
    keep_service: bool = False,
    build_name: Optional[str] = None,
    debug: bool = False,
    resume_session: Optional[PresetAgentSession] = None,
    user_prompt: Optional[str] = None,
    allowed_fleets: Optional[tuple[str, ...]] = None,
) -> PresetCreateResult:
    agent_session = resume_session or create_preset_agent_session(configuration, debug=debug)
    try:
        resolved_configuration = _resolve_preset_env(configuration)
        result = asyncio.run(
            _create_preset(
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
        _close_agent_session(agent_session, "failed")
        raise
    _close_agent_session(agent_session, "success")
    return result


async def _create_preset(
    *,
    api: Client,
    configuration: PresetConfiguration,
    store: PresetStore,
    source_configuration: Optional[PresetConfiguration] = None,
    keep_service: bool = False,
    build_name: Optional[str] = None,
    agent_session: PresetAgentSession,
    resume: bool = False,
    attach: bool = False,
    wait_for_run_stop: bool = True,
    user_prompt: Optional[str] = None,
    allowed_fleets: Optional[tuple[str, ...]] = None,
) -> PresetCreateResult:
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
                "The configuration prompt is ignored when resuming: the preset keeps its original prompt"
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
            raise CLIError(_NO_FLEETS_ERROR)
        auth = get_claude_auth()
        workspace = create_agent_workspace(agent_session)
        build_name = build_name or _get_build_name(
            configuration.name, configuration.model.api_model_name, agent_session.preset_id
        )
    # Record ownership + the finalize context (project, keep-service) so a later
    # detached reconcile can complete this session from disk alone.
    mark_session_owner(
        agent_session,
        project=api.project,
        keep_service=keep_service,
        claude_model=auth.model if auth is not None else None,
    )

    preset_env = configuration.env.as_dict()
    token = getattr(api.client, "_token", None)
    if not isinstance(token, str) or not token:
        raise CLIError("The configured dstack client has no authentication token")
    redacted_values = get_redacted_values(
        [
            token,
            (auth.api_key if auth is not None else None) or "",
            *preset_env.values(),
            *get_sensitive_inherited_env_values(),
        ]
    )
    env: dict[str, str] = {}
    report: Optional[AgentFinalReport] = None
    preset: Optional[Preset] = None
    preset_path: Optional[Path] = None
    creation_succeeded = False
    interrupted = False
    cleanup_error: Optional[str] = None
    if auth is not None:
        env = build_preset_agent_env(
            api=api,
            preset_env=preset_env,
            auth=auth,
            workspace=workspace,
            token=token,
        )
    prompt = get_preset_agent_system_prompt(user_prompt=user_prompt)
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
            process_output = await attach_preset_agent(
                workspace=workspace,
                redacted_values=redacted_values,
                agent_session=agent_session,
            )
            if process_output.report_data is None and not workspace.final_report_path.exists():
                raise AgentExitedWithoutReport(process_output.error)
        else:
            assert auth is not None
            process_output = await run_preset_agent(
                prompt=prompt,
                env=env,
                workspace=workspace,
                auth=auth,
                redacted_values=redacted_values,
                agent_session=agent_session,
                initial_resume_session_id=initial_resume_session_id,
            )
        report = load_preset_agent_report(
            output=process_output,
            workspace=workspace,
            redacted_values=redacted_values,
        )
        run = api.client.runs.get(api.project, report.run_name)
        preset = build_verified_preset(
            run=run,
            preset_configuration=source_configuration,
            report=report,
            preset_id=agent_session.preset_id or None,
            name=claimed_session_name(agent_session.read_manifest()),
        )
        if contains_redacted_value(preset_to_data(preset), redacted_values):
            raise CLIError("Generated preset contains a secret value")
        preset_path = store.save(preset)
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
                    wait_for_stop=wait_for_run_stop,
                )
            except Exception as e:
                cleanup_error = str(e)

    if cleanup_error is not None:
        # The preset is already saved by this point; a failed cleanup only means
        # trial runs may still be running. Warn rather than fail the (successful)
        # session — otherwise a transient blip would discard completed work.
        if agent_session.echo:
            warn(f"Failed to stop preset creation runs: {cleanup_error}")
    assert preset is not None
    assert preset_path is not None
    assert report is not None
    assert report.run_id is not None
    assert report.run_name is not None
    return PresetCreateResult(
        preset=preset,
        path=preset_path,
        final_run_id=report.run_id,
        final_run_name=report.run_name,
    )


def _finish_agent_session(
    session: PresetAgentSession,
    status: str,
) -> None:
    try:
        session.finish(status)
    except OSError as e:
        if session.echo:
            warn(f"Could not finalize agent output. Files remain at {session.path}: {e}")


def _close_agent_session(session: PresetAgentSession, status: str) -> None:
    """Records the terminal status and removes the workspace alias."""
    _finish_agent_session(session, status)
    remove_agent_workspace(session)


def _detach_agent_session(session: PresetAgentSession) -> None:
    """Releases ownership but leaves the agent running — it stays visible and
    reconcilable in `dstack preset`. Silent: `logs -f` calls this on Ctrl+C, and
    a viewer that just stops watching shouldn't announce anything."""
    session.update_manifest(pid=None)


def _stop_or_detach_agent_session(
    session: PresetAgentSession, api: Optional[Client] = None
) -> None:
    """`create` interrupt: stop the session, or detach and leave the agent
    working — it stays visible as a running session in `dstack preset`."""
    manifest = session.read_manifest()
    agent_alive = session_process_alive({**manifest, "pid": None})
    stop = True
    if agent_alive:
        try:
            stop = confirm_ask(f"Stop creating preset [code]{session.preset_id}[/]?")
        except (KeyboardInterrupt, EOFError):
            stop = True
    if not stop:
        _detach_agent_session(session)
        console.print(
            f"\nDetached. Follow with [code]dstack preset logs -f {session.preset_id}[/]"
            f" or stop with [code]dstack preset stop {session.preset_id}[/]."
        )
        return
    terminate_agent_process(manifest)
    if api is not None:
        _stop_active_session_runs(api, session)
    _suspend_agent_session(session)


def _suspend_agent_session(session: PresetAgentSession) -> None:
    try:
        session.finish("interrupted")
    except OSError as e:
        warn(f"Could not record the interrupted preset state: {e}")
    # The kept workspace must not retain a live credential while suspended.
    scrub_workspace_token(session)
    console.print(f"\nPreset [code]{session.preset_id}[/] creation interrupted.")
    console.print(
        f"Resume it with [code]dstack preset create -f <config> --resume {session.preset_id}[/]."
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


def _load_build_name(workspace: PresetAgentWorkspace) -> str:
    try:
        data = json.loads(workspace.constraints_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise CLIError(f"The preset creation constraints cannot be read: {e}") from e
    prefix = data.get("run_name_prefix") if isinstance(data, dict) else None
    if not isinstance(prefix, str) or not prefix:
        raise CLIError("The preset creation constraints do not contain a run name prefix")
    return prefix


def plan_preset(*, api: Client, configuration: PresetConfiguration) -> tuple[str, ...]:
    """Resolves the allowed fleets and shows what the agent will have to work
    with — Project, User, the effective fleets, and their offers. Agent-free."""
    allowed_fleets = _get_allowed_fleets(api, configuration)
    if not allowed_fleets:
        raise CLIError(_NO_FLEETS_ERROR)
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
        job_plan = run_plan.job_plans[0]
        if job_plan.offers:
            print_offers_table(
                offers=job_plan.offers,
                total_offers=job_plan.total_offers,
                max_price=job_plan.max_price or 0.0,
                mute_tail_rows=False,
            )
        else:
            console.print(NO_OFFERS_WARNING)
    except Exception as e:  # noqa: BLE001
        warn(f"Could not list offers for the allowed fleets: {e}")


def _get_allowed_fleets(api: Client, configuration: PresetConfiguration) -> tuple[str, ...]:
    if configuration.fleets is not None:
        return tuple(fleet.format() for fleet in configuration.fleets)
    fleets = api.client.fleets.list(api.project, include_imported=True)
    return tuple(
        fleet.name if fleet.project_name == api.project else f"{fleet.project_name}/{fleet.name}"
        for fleet in fleets
        if fleet.status == FleetStatus.ACTIVE
    )


def _build_constraints(
    *,
    configuration: PresetConfiguration,
    build_name: str,
    allowed_fleets: Sequence[str],
) -> str:
    constraints = PresetConstraints.parse_obj(
        {
            "run_name_prefix": build_name,
            "model": json.loads(configuration.model.json(exclude_none=True)),
            "context_length": configuration.context_length,
            "max_trials": configuration.max_trials,
            "concurrency": configuration.effective_concurrency,
            "fleets": list(allowed_fleets),
            "env": list(configuration.env),
        }
    )
    # All fields are always present; unset optional constraints render as null.
    return json.dumps(json.loads(constraints.json()), indent=2) + "\n"


def _save_final_report_copy(
    *,
    workspace: PresetAgentWorkspace,
    agent_session: PresetAgentSession,
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
    workspace: PresetAgentWorkspace,
    final_run_name: Optional[str],
    agent_session: PresetAgentSession,
    keep_final_service: bool = False,
    wait_for_stop: bool = True,
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
    if not wait_for_stop:
        # Background reconcile issues the stop but must not block the read
        # command it runs inside; the runs terminate on the server regardless.
        return
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
        print_preset_progress("All preset creation runs stopped.", agent_session=agent_session)


def _load_submitted_run_names(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    names = []
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            name = value["name"].strip()
            if name:
                names.append(name)
    return names
