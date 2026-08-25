import asyncio
import dataclasses
import json
import os
import re
import time
import uuid
from contextlib import nullcontext, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Sequence

import yaml
from rich.table import Table
from rich.text import Text

from dstack._internal.cli.models.preset_agent import (
    PresetAgentFailure,
    PresetAgentSuccess,
    PresetSessionFinalize,
    PresetSessionState,
    PresetSessionStatus,
    PresetSessionWorkspace,
)
from dstack._internal.cli.models.presets import VerifiedPreset
from dstack._internal.cli.services.presets.agent import (
    ClaudeAuth,
    PresetAgentProcessOutput,
    attach_preset_agent,
    build_preset_agent_env,
    get_claude_auth,
    run_preset_agent,
    terminate_agent_process,
)
from dstack._internal.cli.services.presets.prompt import get_preset_agent_system_prompt
from dstack._internal.cli.services.presets.redaction import (
    contains_redacted_value,
    get_redacted_values,
    get_sensitive_inherited_env_values,
    redact,
)
from dstack._internal.cli.services.presets.session import (
    PresetSession,
    SessionBusyError,
    claimed_session_name,
    create_preset_session,
    find_session_name_claims,
    iter_preset_sessions,
    load_attachable_session,
    load_preset_session,
    print_preset_progress,
    print_session_log,
    process_alive,
    release_session_claim,
    resolve_session_ref,
    session_process_alive,
    session_report_exists,
    try_claim_session,
)
from dstack._internal.cli.services.presets.store import PresetStore
from dstack._internal.cli.services.presets.verify import (
    build_verified_preset,
    load_preset_agent_report,
)
from dstack._internal.cli.services.presets.workspace import (
    PresetAgentWorkspace,
    attach_agent_workspace,
    create_agent_workspace,
    install_previous_records,
    remove_agent_workspace,
    scrub_workspace_token,
)
from dstack._internal.cli.utils.common import NO_OFFERS_WARNING, confirm_ask, console, warn
from dstack._internal.cli.utils.offers import print_offers_table
from dstack._internal.core.errors import CLIError, ConfigurationError
from dstack._internal.core.models.configurations import (
    PresetConfiguration,
    TaskConfiguration,
)
from dstack._internal.core.models.envs import Env, EnvSentinel
from dstack._internal.core.models.fleets import FleetStatus
from dstack._internal.core.models.presets import (
    PresetConstraints,
    PresetDatasetConstraints,
    PresetRandomConstraints,
)
from dstack._internal.core.models.runs import RunSpec
from dstack._internal.utils.power import prevent_idle_sleep
from dstack.api import Client

_RUN_STOP_TIMEOUT_SECONDS = 10 * 60
_NO_FLEETS_ERROR = "The project has no fleets. Create one before creating a preset"


@dataclass(frozen=True)
class PresetCreateResult:
    preset: VerifiedPreset
    path: Path
    final_run_id: uuid.UUID
    final_run_name: str


class CreationStopped(Exception):
    """Another CLI stopped this creation; it already recorded the interruption."""


class AgentExitedWithoutReport(Exception):
    """A detached agent exited without a report; the session can be resumed."""

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
    """Finalizes a detached session CLI-side (secret-scrubbing and
    server-verified preset building must run here, not on the server).

    Takes the exclusive finalize lock so a concurrent `logs -f` and reconcile
    can't both finalize the same session."""
    session = load_attachable_session(preset_id)
    session.echo = echo
    lock = try_claim_session(session)
    if lock is None:
        raise SessionBusyError(f"Preset {preset_id} is being finalized by another process")
    try:
        configuration = load_session_configuration(session)
        try:
            result = asyncio.run(
                _create_preset(
                    api=api,
                    configuration=_resolve_preset_env(configuration, strict=False),
                    source_configuration=configuration,
                    store=store,
                    keep_service=keep_service,
                    session=session,
                    mode="attach",
                    wait_for_run_stop=wait_for_run_stop,
                )
            )
        except KeyboardInterrupt:
            # `logs -f` is a viewer: Ctrl+C detaches and leaves the agent
            # running (reconcile finalizes it later), never stops it.
            _detach_agent_session(session)
            raise
        except AgentExitedWithoutReport as e:
            _stop_active_session_runs(api, session)
            _suspend_agent_session(session)
            raise CLIError(str(e)) from e
        except CLIError:
            # A CLIError is definitive (bad report, unverifiable service, leaked
            # secret): the preset cannot be built, so fail it.
            _close_agent_session(session, "failed")
            raise
        # A transient error (network / OS) propagates untouched: the completed
        # session and its report stay intact for a later follow or reconcile.
        _close_agent_session(session, "success")
        return result
    finally:
        release_session_claim(lock)


def load_session_configuration(session: PresetSession) -> PresetConfiguration:
    configuration_path = session.path / "preset.dstack.yml"
    if not configuration_path.is_file():
        raise CLIError(
            f"Preset {session.preset_id} has no saved configuration and cannot be"
            f" followed; run `dstack preset resume {session.preset_id}` instead"
        )
    try:
        data = yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
        # A session started before the `random` alias was retired legally saved
        # it; the rejection is for fresh configurations, not this record.
        if isinstance(data, dict) and data.get("dataset") == "random":
            data = {key: value for key, value in data.items() if key != "dataset"}
        return PresetConfiguration.model_validate(data)
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
    session = load_preset_session(preset_id)
    state = session.read_state()
    if not follow or state is None or state.status in ("success", "failed", "interrupted"):
        print_session_log(session)
        return None
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


def _follow_session_log_readonly(session: PresetSession) -> None:
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
        state = session.read_state()
        if state is None or state.status in ("success", "failed", "interrupted"):
            return
        if not chunk and not session_process_alive(state):
            # The owner died without recording a terminal status; stop tailing
            # rather than poll forever.
            console.print(
                f"The process creating preset [code]{session.preset_id}[/] exited;"
                f" follow it again with [code]dstack preset logs -f {session.preset_id}[/]"
            )
            return
        time.sleep(1)


def reconcile_detached_sessions(store: PresetStore) -> None:
    """Finalizes sessions whose agent completed while no CLI was attached, so
    the saved preset never depends on a foreground process staying alive.

    Best-effort and parallel-safe: finalize takes an exclusive claim, and every
    error is swallowed so the calling read command never fails."""
    for session in iter_preset_sessions():
        if _is_reconcilable(session.read_state()):
            _reconcile_session(session, store)


def _is_reconcilable(state: Optional[PresetSessionState]) -> bool:
    # An orphaned session (no live owner) whose agent left a completion report.
    # Sessions created before finalize context was persisted lack `project` and
    # are skipped — they finalize interactively via `logs -f`.
    return (
        state is not None
        and state.status == "running"
        and state.run is not None
        and session_report_exists(state)
        and not session_process_alive(state)
    )


def _reconcile_session(session: PresetSession, store: PresetStore) -> None:
    state = session.read_state()
    if state is None or state.run is None:
        return
    try:
        api = Client.from_config(project_name=state.run.finalize.project)
    except Exception:  # noqa: BLE001 — offline/misconfigured must not break the read command
        return
    # follow_preset records the terminal status and is claim-safe; suppress every
    # error and stay silent here since the result shows up in the list that follows.
    with suppress(Exception):
        follow_preset(
            api=api,
            store=store,
            preset_id=session.preset_id,
            keep_service=state.run.finalize.keep_service,
            wait_for_run_stop=False,
            echo=False,
        )


def stop_preset_session(api: Client, preset_id: str) -> None:
    session = load_preset_session(preset_id)
    state = session.read_state()
    if state is None:
        raise CLIError(f"Preset {preset_id} session state is unreadable")
    status = state.status
    if status == "success":
        console.print(f"Preset [code]{preset_id}[/] is already created")
        return
    if status == "failed":
        console.print(f"Preset [code]{preset_id}[/] creation failed")
        return
    if status == "interrupted":
        console.print(f"Preset [code]{preset_id}[/] creation was interrupted.")
        return
    if session_report_exists(state) and not session_process_alive(state):
        # The agent already finished; finalize like reconcile would instead of
        # leaving a not-yet-saved intermediate state behind.
        follow_preset(
            api=api,
            store=PresetStore(),
            preset_id=preset_id,
            keep_service=state.run.finalize.keep_service if state.run else False,
            echo=False,
        )
        console.print(f"Preset [code]{preset_id}[/] is already created")
        return
    # Stop wins, like `dstack stop`: record the intent first so a live owner's
    # retry loop exits instead of resurrecting the agent, then terminate.
    _finish_agent_session(session, "interrupted")
    terminate_agent_process(state.run.agent if state.run else None)
    _stop_active_session_runs(api, session)
    _suspend_agent_session(session)


def _stop_active_session_runs(api: Client, session: PresetSession) -> None:
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
    """Non-strict mode drops unresolvable `EnvSentinel` entries instead of
    raising — for attach, where env values only feed redaction and the agent
    already runs."""
    configuration = configuration.model_copy(deep=True)
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
    configuration.env = Env.model_validate(resolved)
    return configuration


def resolve_previous_sessions(refs: Sequence[str]) -> tuple[PresetSession, ...]:
    sessions: list[PresetSession] = []
    for ref in refs:
        try:
            session = load_preset_session(resolve_session_ref(ref))
        except CLIError:
            raise CLIError(f"Previous session {ref!r} does not exist")
        if all(existing.preset_id != session.preset_id for existing in sessions):
            sessions.append(session)
    included = {session.preset_id for session in sessions}
    for session in sessions:
        state = session.read_state()
        if state is None:
            raise CLIError(f"Previous session {session.preset_id} state is unreadable")
        if state.status == "running" and session_process_alive(state):
            raise CLIError(
                f"Previous session {session.preset_id} is still running;"
                " wait for it to finish or stop it"
            )
        for parent in state.previous:
            if parent not in included:
                warn(
                    f"{session.preset_id} was created with --previous {parent},"
                    " which is not included"
                )
    return tuple(sessions)


def _load_pinned_previous_sessions(ids: Sequence[str]) -> tuple[PresetSession, ...]:
    sessions = []
    for preset_id in ids:
        try:
            sessions.append(load_preset_session(preset_id))
        except CLIError:
            warn(f"Previous session {preset_id} no longer exists; keeping its copied records")
    return tuple(sessions)


def create_preset(
    *,
    api: Client,
    configuration: PresetConfiguration,
    store: PresetStore,
    keep_service: bool = False,
    build_name: Optional[str] = None,
    resume_session: Optional[PresetSession] = None,
    user_prompt: Optional[str] = None,
    allowed_fleets: Optional[tuple[str, ...]] = None,
    previous: Sequence[PresetSession] = (),
) -> PresetCreateResult:
    session = resume_session or create_preset_session(
        configuration,
        previous=tuple(session.preset_id for session in previous),
    )
    try:
        resolved_configuration = _resolve_preset_env(configuration)
        # A creation session runs unattended for hours; an idling machine would
        # freeze the agent and the process supervising it alike.
        with prevent_idle_sleep():
            result = asyncio.run(
                _create_preset(
                    api=api,
                    configuration=resolved_configuration,
                    source_configuration=configuration,
                    store=store,
                    keep_service=keep_service,
                    build_name=build_name,
                    session=session,
                    mode="resume" if resume_session is not None else "fresh",
                    user_prompt=user_prompt,
                    allowed_fleets=allowed_fleets,
                    previous=previous,
                )
            )
    except KeyboardInterrupt:
        _stop_or_detach_agent_session(session, api)
        raise
    except CreationStopped:
        # The stopping CLI already suspended the session.
        raise
    except BaseException:
        _close_agent_session(session, "failed")
        raise
    _close_agent_session(session, "success")
    return result


@dataclass(frozen=True)
class _CreationSetup:
    """Per-mode inputs to the shared creation path, built by one of
    `_fresh_setup`, `_resume_setup`, or `_attach_setup`."""

    auth: Optional[ClaudeAuth]
    workspace: PresetAgentWorkspace
    workspace_record: PresetSessionWorkspace
    build_name: str
    allowed_fleets: tuple[str, ...]
    user_prompt: Optional[str]
    initial_resume_session_id: Optional[str]
    write_constraints: bool  # True only for fresh creations
    previous: tuple[str, ...] = ()  # session IDs, pinned at creation


def _fresh_setup(
    api: Client,
    configuration: PresetConfiguration,
    session: PresetSession,
    build_name: Optional[str],
    allowed_fleets: Optional[tuple[str, ...]],
    user_prompt: Optional[str],
    previous: Sequence[PresetSession],
) -> _CreationSetup:
    if allowed_fleets is None:
        allowed_fleets = _get_allowed_fleets(api, configuration)
    if not allowed_fleets:
        raise CLIError(_NO_FLEETS_ERROR)
    auth = get_claude_auth()
    workspace, workspace_record = create_agent_workspace(session)
    previous_ids = tuple(session.preset_id for session in previous)
    if previous_ids:
        install_previous_records(workspace, previous)
    build_name = build_name or _get_build_name(
        configuration.name, configuration.model.api_model_name, session.preset_id
    )
    return _CreationSetup(
        auth=auth,
        workspace=workspace,
        workspace_record=workspace_record,
        build_name=build_name,
        allowed_fleets=allowed_fleets,
        user_prompt=user_prompt,
        initial_resume_session_id=None,
        write_constraints=True,
        previous=previous_ids,
    )


def _resume_setup(
    session: PresetSession,
    build_name: Optional[str],
    user_prompt: Optional[str],
) -> _CreationSetup:
    # The prompt is fixed at session creation, like the constraints.
    pinned_prompt = session.read_user_prompt()
    if user_prompt is not None and user_prompt != pinned_prompt:
        warn(
            "The configuration prompt is ignored when resuming: the preset keeps its original prompt"
        )
    user_prompt = pinned_prompt
    auth = get_claude_auth()
    workspace, workspace_record = attach_agent_workspace(session)
    state = session.read_state()
    if state is None or state.run is None:
        raise CLIError(f"Preset {session.preset_id} session state is unreadable")
    if state.run.claude_model:
        auth = dataclasses.replace(auth, model=state.run.claude_model)
    initial_resume_session_id = state.run.claude_session_id
    previous_ids = tuple(state.previous)
    if previous_ids:
        install_previous_records(workspace, _load_pinned_previous_sessions(previous_ids))
    return _CreationSetup(
        auth=auth,
        workspace=workspace,
        workspace_record=workspace_record,
        build_name=build_name or _load_build_name(workspace),
        allowed_fleets=(),
        user_prompt=user_prompt,
        initial_resume_session_id=initial_resume_session_id,
        write_constraints=False,
        previous=previous_ids,
    )


def _attach_setup(
    session: PresetSession,
    build_name: Optional[str],
) -> _CreationSetup:
    workspace, workspace_record = attach_agent_workspace(session)
    return _CreationSetup(
        auth=None,
        workspace=workspace,
        workspace_record=workspace_record,
        build_name=build_name or _load_build_name(workspace),
        allowed_fleets=(),
        user_prompt=None,
        initial_resume_session_id=None,
        write_constraints=False,
        previous=_read_previous_ids(session),
    )


async def _create_preset(
    *,
    api: Client,
    configuration: PresetConfiguration,
    store: PresetStore,
    source_configuration: PresetConfiguration,
    keep_service: bool = False,
    build_name: Optional[str] = None,
    session: PresetSession,
    mode: Literal["fresh", "resume", "attach"] = "fresh",
    wait_for_run_stop: bool = True,
    user_prompt: Optional[str] = None,
    allowed_fleets: Optional[tuple[str, ...]] = None,
    previous: Sequence[PresetSession] = (),
) -> PresetCreateResult:
    if mode == "attach":
        setup = _attach_setup(session, build_name)
    elif mode == "resume":
        setup = _resume_setup(session, build_name, user_prompt)
    else:
        setup = _fresh_setup(
            api, configuration, session, build_name, allowed_fleets, user_prompt, previous
        )
    # Take ownership and record the run whole: workspace, finalize context, and
    # the model pin, so a later detached reconcile or resume works from disk alone.
    session.begin_run(
        workspace=setup.workspace_record,
        finalize=PresetSessionFinalize(project=api.project, keep_service=keep_service),
        claude_model=setup.auth.model if setup.auth is not None else None,
    )

    preset_env = configuration.env.as_dict()
    token = api.client.token
    if not token:
        raise CLIError("The configured dstack client has no authentication token")
    redacted_values = get_redacted_values(
        [
            token,
            (setup.auth.api_key if setup.auth is not None else None) or "",
            # Passthrough values are resolved from the caller's environment and
            # are secrets; literal values are the user's own configuration text.
            # The passthrough keys come from the source configuration, since
            # `configuration` here is the resolved copy with no sentinels left.
            *(
                preset_env[key]
                for key, value in source_configuration.env.items()
                if isinstance(value, EnvSentinel) and key in preset_env
            ),
            *get_sensitive_inherited_env_values(),
        ]
    )
    env: dict[str, str] = {}
    report: Optional[PresetAgentSuccess] = None
    preset: Optional[VerifiedPreset] = None
    preset_path: Optional[Path] = None
    creation_succeeded = False
    interrupted = False
    cleanup_error: Optional[str] = None
    if setup.auth is not None:
        env = build_preset_agent_env(
            api=api,
            preset_env=preset_env,
            auth=setup.auth,
            workspace=setup.workspace,
            token=token,
        )
    prompt = get_preset_agent_system_prompt(
        user_prompt=setup.user_prompt,
        baseline=configuration.effective_baseline,
        previous=setup.previous,
        custom_dataset=configuration.dataset is not None,
    )
    if setup.write_constraints:
        if setup.user_prompt:
            session.write_user_prompt(setup.user_prompt)
        constraints_text = _build_constraints(
            configuration=configuration,
            build_name=setup.build_name,
            allowed_fleets=setup.allowed_fleets,
        )
        setup.workspace.constraints_path.write_text(constraints_text, encoding="utf-8")
        # A second, persistent copy: the workspace above is deleted with the run,
        # while the listing and `--previous` read constraints from the session dir.
        session.write_constraints(constraints_text)
        session.write_prompt(prompt)
        if setup.auth is not None:
            session.write_agent_info(setup.auth)
    try:
        if mode == "attach":
            process_output = await attach_preset_agent(
                workspace=setup.workspace,
                redacted_values=redacted_values,
                session=session,
            )
            _raise_if_externally_stopped(session, process_output)
            if (
                process_output.report_data is None
                and not setup.workspace.final_report_path.exists()
            ):
                raise AgentExitedWithoutReport(process_output.error)
        else:
            assert setup.auth is not None
            process_output = await run_preset_agent(
                prompt=prompt,
                env=env,
                workspace=setup.workspace,
                auth=setup.auth,
                redacted_values=redacted_values,
                session=session,
                initial_resume_session_id=setup.initial_resume_session_id,
            )
            _raise_if_externally_stopped(session, process_output)
        result = load_preset_agent_report(
            output=process_output,
            workspace=setup.workspace,
            redacted_values=redacted_values,
        )
        if isinstance(result, PresetAgentFailure):
            raise CLIError(result.failure_summary or "Claude did not create a preset")
        report = result
        run = api.client.runs.get(api.project, report.run_name)
        preset = build_verified_preset(
            run=run,
            preset_configuration=source_configuration,
            report=report,
            workspace_path=setup.workspace.path,
            session_path=session.path,
            preset_id=session.preset_id,
            name=_read_claimed_name(session),
            created_at=session.created_at,
        )
        if contains_redacted_value(preset.model_dump(mode="json"), redacted_values):
            raise CLIError("Generated preset contains a secret value")
        preset_path = store.save(preset)
        creation_succeeded = True
    except (KeyboardInterrupt, asyncio.CancelledError):
        interrupted = True
        raise
    finally:
        _save_final_report_copy(
            workspace=setup.workspace,
            session=session,
            redacted_values=redacted_values,
        )
        if not interrupted:
            keep_final_service = keep_service and creation_succeeded
            try:
                await _cleanup_runs(
                    api=api,
                    build_name=setup.build_name,
                    workspace=setup.workspace,
                    final_run_name=report.run_name if report is not None else None,
                    keep_final_service=keep_final_service,
                    session=session,
                    wait_for_stop=wait_for_run_stop,
                )
            except Exception as e:
                cleanup_error = str(e)

    if cleanup_error is not None:
        # The preset is already saved; a failed cleanup only means trial runs may
        # still be running. Warn rather than fail — else a blip discards the work.
        if session.echo:
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


def _read_previous_ids(session: PresetSession) -> tuple[str, ...]:
    state = session.read_state()
    return tuple(state.previous) if state is not None else ()


def _read_claimed_name(session: PresetSession) -> Optional[str]:
    state = session.read_state()
    return claimed_session_name(state) if state is not None else None


def _raise_if_externally_stopped(
    session: PresetSession, output: "PresetAgentProcessOutput"
) -> None:
    state = session.read_state()
    if output.report_data is None and state is not None and state.status == "interrupted":
        raise CreationStopped


def _finish_agent_session(
    session: PresetSession,
    status: PresetSessionStatus,
) -> None:
    try:
        session.finish(status)
    except OSError as e:
        if session.echo:
            warn(f"Could not finalize agent output. Files remain at {session.path}: {e}")


def _close_agent_session(session: PresetSession, status: Literal["success", "failed"]) -> None:
    _finish_agent_session(session, status)
    remove_agent_workspace(session)


def _detach_agent_session(session: PresetSession) -> None:
    """Releases ownership but leaves the agent running (still reconcilable in
    `dstack preset`), and stays silent since `logs -f` calls this on Ctrl+C."""
    session.detach()


def _stop_or_detach_agent_session(session: PresetSession, api: Client) -> None:
    """`create` interrupt: stop the session, or detach and leave the agent
    working as a running session in `dstack preset`."""
    state = session.read_state()
    agent_alive = state is not None and state.run is not None and process_alive(state.run.agent)
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
    if state is not None:
        terminate_agent_process(state.run.agent if state.run else None)
    _stop_active_session_runs(api, session)
    _suspend_agent_session(session)


def _suspend_agent_session(session: PresetSession) -> None:
    try:
        session.finish("interrupted")
    except OSError as e:
        warn(f"Could not record the interrupted preset state: {e}")
    # The kept workspace must not retain a live credential while suspended.
    scrub_workspace_token(session)
    console.print(f"\nPreset [code]{session.preset_id}[/] creation interrupted.")
    console.print(f"Resume it with [code]dstack preset resume {session.preset_id}[/].")


def _get_build_name(name: Optional[str], model_name: str, suffix: str) -> str:
    base = name or _model_slug(model_name)
    # Leave room for the preset id and numeric submission suffix while retaining
    # a recognizable prefix.
    prefix = base[:26].rstrip("-")
    return f"{prefix}-{suffix}"


def _model_slug(model_name: str) -> str:
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


@dataclass(frozen=True)
class PresetNameHolders:
    """Current claims on a preset name: at most one saved preset, plus any
    creation sessions claiming it (excluding the holder preset's own session)."""

    name: str
    preset: Optional[VerifiedPreset]
    sessions: list[PresetSession]

    @property
    def preset_ids(self) -> list[str]:
        ids = [self.preset.id] if self.preset is not None else []
        ids.extend(session.preset_id for session in self.sessions)
        return ids


def find_preset_name_holders(store: PresetStore, name: str) -> PresetNameHolders:
    preset = store.find_by_name(name)
    sessions = [
        session
        for session in find_session_name_claims(name)
        if preset is None or session.preset_id != preset.id
    ]
    return PresetNameHolders(name=name, preset=preset, sessions=sessions)


def reassign_preset_name(store: PresetStore, holders: PresetNameHolders) -> None:
    if holders.preset is not None:
        store.release_name(holders.name)
    for session in holders.sessions:
        session.release_name()


def plan_preset(*, api: Client, configuration: PresetConfiguration) -> tuple[str, ...]:
    """Agent-free preview of the fleets and offers the agent would be given."""
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
            run_plan = api.client.runs.get_plan(
                api.project, run_spec, max_offers=10, for_offers_only=True
            )
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
    if configuration.dataset is None:
        constraints: PresetConstraints = PresetRandomConstraints(
            run_name_prefix=build_name,
            model=configuration.model,
            min_context_length=configuration.min_context_length,
            max_ttft=configuration.max_ttft,
            trials_num=configuration.trials,
            concurrency=configuration.concurrency,
            input_tokens=configuration.effective_input_tokens,
            output_tokens=configuration.effective_output_tokens,
            shared_prefix_tokens=configuration.shared_prefix_tokens or 0,
            baseline=configuration.effective_baseline,
            fleets=list(allowed_fleets),
            env=list(configuration.env),
        )
    else:
        constraints = PresetDatasetConstraints(
            run_name_prefix=build_name,
            model=configuration.model,
            min_context_length=configuration.min_context_length,
            max_ttft=configuration.max_ttft,
            trials_num=configuration.trials,
            concurrency=configuration.concurrency,
            dataset=configuration.dataset,
            baseline=configuration.effective_baseline,
            fleets=list(allowed_fleets),
            env=list(configuration.env),
        )
    return constraints.model_dump_json(exclude_none=True, indent=2) + "\n"


def _save_final_report_copy(
    *,
    workspace: PresetAgentWorkspace,
    session: PresetSession,
    redacted_values: Sequence[str],
) -> None:
    if not workspace.final_report_path.exists():
        return
    try:
        report_text = workspace.final_report_path.read_text(encoding="utf-8", errors="replace")
        session.write_final_report(redact(report_text, redacted_values))
    except OSError as e:
        warn(f"Could not save a final report copy: {e}")


async def _cleanup_runs(
    *,
    api: Client,
    build_name: str,
    workspace: PresetAgentWorkspace,
    final_run_name: Optional[str],
    session: PresetSession,
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
    # Without a spinner the CLI looks hung while the runs terminate.
    spinner = console.status("Stopping runs...") if session.echo else nullcontext()
    with spinner:
        while pending:
            if asyncio.get_running_loop().time() >= deadline:
                raise CLIError(f"Timed out waiting for runs to stop: {', '.join(sorted(pending))}")
            for name in list(pending):
                run = api.runs.get(name)
                if run is None or run.status.is_finished():
                    pending.remove(name)
            if pending:
                await asyncio.sleep(2)
    print_preset_progress("All preset creation runs stopped.", session=session)


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
