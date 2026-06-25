import argparse
import base64
import sys
import time
from collections import deque
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, cast

from dstack._internal.cli.services.configurators.run import (
    ServiceConfigurator,
    _print_service_urls,
)
from dstack._internal.cli.utils.common import confirm_ask, console
from dstack._internal.core.models.configurations import ServiceConfiguration, TaskConfiguration
from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.harness.generator import (
    regenerate_service_configuration,
    save_service_configuration,
)
from dstack._internal.harness.models import EndpointCreateParams
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack.api._public import Client

# Markers that indicate the model server finished starting and is serving.
READY_PATTERNS = (
    "Application startup complete",
    "Uvicorn running on",
    "The server is fired up and ready to roll",  # SGLang
    "Connected",  # TGI
)
# Markers that indicate a fatal container error before the server became ready.
FATAL_PATTERNS = (
    "Traceback (most recent call last)",
    "Engine core initialization failed",
    "EngineCore failed to start",
    "RuntimeError",
    "CUDA out of memory",
    "torch.cuda.OutOfMemoryError",
)

DEFAULT_MONITOR_TIMEOUT_SECS = 1800
MONITOR_POLL_INTERVAL_SECS = 3
MAX_ERROR_LOG_CHARS = 6000


class _Outcome(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


def deploy_service_configuration(
    api: Client,
    configuration: ServiceConfiguration,
    configuration_path: Path,
    command_args: argparse.Namespace,
    configurator_args: argparse.Namespace,
) -> None:
    """Submit a service detached and report status (no self-healing)."""
    _submit_detached(api, configuration, configuration_path, command_args, configurator_args)
    if configuration.name:
        _wait_for_service_and_report(api, configuration.name)


def deploy_service_with_self_healing(
    api: Client,
    configuration: ServiceConfiguration,
    params: EndpointCreateParams,
    configuration_path: Path,
    command_args: argparse.Namespace,
    configurator_args: argparse.Namespace,
    skill_path: Optional[str] = None,
    max_attempts: int = 3,
    monitor_timeout_secs: int = DEFAULT_MONITOR_TIMEOUT_SECS,
) -> None:
    """Submit, monitor logs, and on failure stop, ask the LLM to fix, and redeploy."""
    config_path = configuration_path
    try:
        _run_self_healing_loop(
            api=api,
            configuration=configuration,
            params=params,
            config_path=config_path,
            command_args=command_args,
            configurator_args=configurator_args,
            skill_path=skill_path,
            max_attempts=max_attempts,
            monitor_timeout_secs=monitor_timeout_secs,
        )
    except KeyboardInterrupt:
        _handle_detach_on_interrupt(api, configuration.name, command_args.yes)


def _print_monitoring_message(run_name: str) -> None:
    console.print(f"[code]\\[harness][/] Monitoring logs for [code]{run_name}[/]...")


def _run_self_healing_loop(
    api: Client,
    configuration: ServiceConfiguration,
    params: EndpointCreateParams,
    config_path: Path,
    command_args: argparse.Namespace,
    configurator_args: argparse.Namespace,
    skill_path: Optional[str],
    max_attempts: int,
    monitor_timeout_secs: int,
) -> None:
    detach = command_args.detach
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            console.print(
                f"\n[code]\\[harness][/] Attempt {attempt}/{max_attempts}:"
                " redeploying updated configuration..."
            )

        if not configuration.name:
            return

        # Auto-confirm on retries; the user already approved the first plan.
        submit_args = argparse.Namespace(
            yes=command_args.yes or attempt > 1,
            detach=detach,
            verbose=command_args.verbose,
            force=command_args.force,
            pre_attach_hook=_print_monitoring_message if not detach else None,
        )
        token_before = _submission_token(api, configuration.name)
        configurator = ServiceConfigurator(api_client=api)
        try:
            configurator.apply_configuration(
                conf=configuration,
                configuration_path=str(config_path),
                command_args=submit_args,
                configurator_args=configurator_args,
            )
        except SystemExit as e:
            if detach or e.code in (0, None):
                raise
            if attempt == max_attempts:
                console.print(
                    f"[code]\\[harness][/] Reached the maximum of {max_attempts} attempts."
                    " Giving up. See the logs above for the last error."
                )
                raise
            console.print(
                f"[code]\\[harness][/] Detected a failure on attempt {attempt}."
                f" Stopping run [code]{configuration.name}[/]..."
            )
            error_logs = _fetch_recent_logs(api, configuration.name)
            # Stop the failed run so the next attempt is a clean fresh deployment.
            # Otherwise dstack treats the redeploy as an in-place rolling update of
            # the still-active service, which breaks the attached log stream.
            _stop_run(api, configuration.name)
            console.print(
                "[code]\\[harness][/] Asking the model to fix the configuration based on the error..."
            )
            configuration, config_path = _regenerate_configuration(
                api=api,
                configuration=configuration,
                params=params,
                config_path=config_path,
                configurator_args=configurator_args,
                error_logs=error_logs,
                skill_path=skill_path,
            )
            continue

        # If no new submission was created, the user declined the plan (or there
        # was nothing to apply). That is a clean exit, not a deployment failure.
        token_after = _submission_token(api, configuration.name)
        if token_after is None or token_after == token_before:
            return

        if detach:
            console.print(
                f"[code]\\[harness][/] Monitoring logs for [code]{configuration.name}[/]..."
            )
            outcome, error_logs = _monitor_run(api, configuration.name, monitor_timeout_secs)
        else:
            # Attached apply streams logs via dstack until the user detaches or the run ends.
            return

        if outcome is _Outcome.SUCCESS:
            run = api.runs.get(configuration.name)
            if run is not None:
                run.refresh()
                _print_service_urls(run)
            console.print(
                f"[code]\\[harness][/] Endpoint [code]{configuration.name}[/] is up and serving."
            )
            return

        if outcome is _Outcome.TIMEOUT:
            console.print(
                f"[code]\\[harness][/] Timed out waiting for [code]{configuration.name}[/]"
                " to become ready. Stopping the run."
            )
            _stop_run(api, configuration.name)
            return

        console.print(
            f"[code]\\[harness][/] Detected a failure on attempt {attempt}."
            f" Stopping run [code]{configuration.name}[/]..."
        )
        _stop_run(api, configuration.name)

        if attempt == max_attempts:
            console.print(
                f"[code]\\[harness][/] Reached the maximum of {max_attempts} attempts."
                " Giving up. See the logs above for the last error."
            )
            return

        console.print(
            "[code]\\[harness][/] Asking the model to fix the configuration based on the error..."
        )
        configuration, config_path = _regenerate_configuration(
            api=api,
            configuration=configuration,
            params=params,
            config_path=config_path,
            configurator_args=configurator_args,
            error_logs=error_logs,
            skill_path=skill_path,
        )


def _regenerate_configuration(
    api: Client,
    configuration: ServiceConfiguration,
    params: EndpointCreateParams,
    config_path: Path,
    configurator_args: argparse.Namespace,
    error_logs: str,
    skill_path: Optional[str],
) -> tuple[ServiceConfiguration, Path]:
    previous_yaml = config_path.read_text(encoding="utf-8")
    configuration = regenerate_service_configuration(
        params=params,
        previous_yaml=previous_yaml,
        error_logs=error_logs,
        skill_path=skill_path,
    )
    ServiceConfigurator(api_client=api).apply_args(
        cast(TaskConfiguration, configuration), configurator_args
    )
    config_path = save_service_configuration(configuration)
    console.print(f"[code]\\[harness][/] Saved updated configuration to [code]{config_path}[/]")
    return configuration, config_path


def _fetch_recent_logs(api: Client, run_name: str) -> str:
    run = api.runs.get(run_name)
    if run is None:
        return ""
    try:
        submission = run._run.jobs[0].job_submissions[-1]
    except (AttributeError, IndexError):
        return ""
    events = _poll_new_logs(api, run_name, submission.id, None)
    text = "".join(base64.b64decode(event.message).decode(errors="replace") for event in events)
    return _truncate_logs(text)


def _truncate_logs(text: str) -> str:
    if len(text) > MAX_ERROR_LOG_CHARS:
        return text[-MAX_ERROR_LOG_CHARS:]
    return text


def _handle_detach_on_interrupt(api: Client, run_name: Optional[str], yes: bool) -> None:
    if not run_name:
        return
    run = api.runs.get(run_name)
    if run is None or run.status.is_finished():
        return
    try:
        if yes or not confirm_ask(f"\nStop the run [code]{run_name}[/] before detaching?"):
            console.print("Detached")
            return
        with console.status("Stopping..."):
            api.client.runs.stop(api.project, [run_name], False)
            while True:
                run = api.runs.get(run_name)
                if run is None or run.status.is_finished():
                    break
                time.sleep(2)
        console.print("Stopped")
    except KeyboardInterrupt:
        with console.status("Aborting..."):
            api.client.runs.stop(api.project, [run_name], True)
        console.print("[error]Aborted[/]")


def _submit_detached(
    api: Client,
    configuration: ServiceConfiguration,
    configuration_path: Path,
    command_args: argparse.Namespace,
    configurator_args: argparse.Namespace,
) -> None:
    configurator = ServiceConfigurator(api_client=api)
    submit_args = argparse.Namespace(
        yes=command_args.yes,
        detach=True,
        verbose=command_args.verbose,
        force=command_args.force,
    )
    configurator.apply_configuration(
        conf=configuration,
        configuration_path=str(configuration_path),
        command_args=submit_args,
        configurator_args=configurator_args,
    )


def _submission_token(api: Client, run_name: str) -> Optional[tuple]:
    """Identify the latest run submission so we can tell if a new run was submitted.

    Returns None when the run does not exist. When `apply` is declined or makes no
    change, the token is unchanged; a fresh submission produces a different token.
    """
    run = api.runs.get(run_name)
    if run is None:
        return None
    run_id = getattr(run._run, "id", None)
    try:
        submission = run._run.jobs[0].job_submissions[-1]
    except (AttributeError, IndexError):
        return (str(run_id), None, None)
    return (str(run_id), str(submission.id), submission.deployment_num)


def _monitor_run(api: Client, run_name: str, timeout_secs: int) -> tuple[_Outcome, str]:
    deadline = time.monotonic() + timeout_secs
    log_tail: deque[str] = deque(maxlen=300)
    last_timestamp = None
    ready_seen = False
    fatal_seen = False

    while time.monotonic() < deadline:
        run = api.runs.get(run_name)
        if run is None:
            return _Outcome.FAILED, _format_tail(log_tail)

        submission = run._run.jobs[0].job_submissions[-1]
        events = _poll_new_logs(api, run_name, submission.id, last_timestamp)
        for event in events:
            text = base64.b64decode(event.message).decode(errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            log_tail.append(text)
            if any(pattern in text for pattern in READY_PATTERNS):
                ready_seen = True
            if any(pattern in text for pattern in FATAL_PATTERNS):
                fatal_seen = True
            last_timestamp = event.timestamp

        if run.status in (RunStatus.FAILED, RunStatus.TERMINATED) or (
            submission.status == JobStatus.FAILED
        ):
            return _Outcome.FAILED, _format_tail(log_tail)

        if ready_seen and submission.status == JobStatus.RUNNING:
            return _Outcome.SUCCESS, _format_tail(log_tail)

        if fatal_seen and not ready_seen:
            return _Outcome.FAILED, _format_tail(log_tail)

        time.sleep(MONITOR_POLL_INTERVAL_SECS)

    return _Outcome.TIMEOUT, _format_tail(log_tail)


def _poll_new_logs(api: Client, run_name: str, submission_id, start_time):
    if start_time is not None:
        start_time = start_time + timedelta(microseconds=1)
    events = []
    next_token = None
    while True:
        resp = api.client.logs.poll(
            project_name=api.project,
            body=PollLogsRequest(
                run_name=run_name,
                job_submission_id=submission_id,
                start_time=start_time,
                end_time=None,
                descending=False,
                limit=1000,
                diagnose=False,
                next_token=next_token,
            ),
        )
        events.extend(resp.logs)
        next_token = resp.next_token
        if next_token is None:
            break
    return events


def _format_tail(log_tail: deque) -> str:
    return _truncate_logs("".join(log_tail))


def _stop_run(api: Client, run_name: str) -> None:
    with console.status(f"Stopping {run_name}..."):
        api.client.runs.stop(api.project, [run_name], False)
        while True:
            run = api.runs.get(run_name)
            if run is None or run.status.is_finished():
                break
            time.sleep(2)
    console.print(f"[code]\\[harness][/] Stopped [code]{run_name}[/]")


def _wait_for_service_and_report(api: Client, run_name: str, attempts: int = 30) -> None:
    for _ in range(attempts):
        run = api.runs.get(run_name)
        if run is None:
            return
        if run.status in (RunStatus.RUNNING, RunStatus.DONE, RunStatus.FAILED):
            console.print()
            run.refresh()
            _print_service_urls(run)
            if run.status == RunStatus.FAILED:
                console.print(
                    f"[error]Run [code]{run_name}[/] failed. Check [code]dstack logs {run_name}[/]."
                )
            return
        time.sleep(2)

    console.print(
        f"Run [code]{run_name}[/] is still provisioning. Check status with [code]dstack ps -v[/]."
    )
