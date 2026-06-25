import argparse
import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock

from dstack._internal.core.models.runs import JobStatus, RunStatus
from dstack._internal.harness import deployer
from dstack._internal.harness.deployer import (
    _handle_detach_on_interrupt,
    _monitor_run,
    _Outcome,
    _run_self_healing_loop,
    _submission_token,
)
from dstack._internal.harness.models import EndpointCreateParams


def _log_event(message: str, ts: datetime) -> MagicMock:
    event = MagicMock()
    event.message = base64.b64encode(message.encode()).decode()
    event.timestamp = ts
    return event


def _make_api(statuses, logs_per_poll):
    """Build a fake Client whose run status and logs change per monitor iteration."""
    api = MagicMock()
    api.project = "main"

    state = {"i": 0}

    def get_run(_name):
        idx = min(state["i"], len(statuses) - 1)
        run_status, job_status = statuses[idx]
        run = MagicMock()
        run.status = run_status
        submission = MagicMock()
        submission.status = job_status
        submission.id = "11111111-1111-4111-8111-111111111111"
        run._run.jobs = [MagicMock(job_submissions=[submission])]
        return run

    api.runs.get.side_effect = get_run

    def poll(project_name, body):
        idx = min(state["i"], len(logs_per_poll) - 1)
        resp = MagicMock()
        resp.logs = logs_per_poll[idx]
        resp.next_token = None
        state["i"] += 1
        return resp

    api.client.logs.poll.side_effect = poll
    return api


class TestMonitorRun:
    def test_detects_success_on_ready_marker(self, monkeypatch):
        monkeypatch.setattr(deployer.time, "sleep", lambda _s: None)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        statuses = [
            (RunStatus.RUNNING, JobStatus.RUNNING),
            (RunStatus.RUNNING, JobStatus.RUNNING),
        ]
        logs = [
            [_log_event("Loading model...\n", ts)],
            [_log_event("INFO: Application startup complete\n", ts)],
        ]
        api = _make_api(statuses, logs)

        outcome, _ = _monitor_run(api, "svc", timeout_secs=60)
        assert outcome is _Outcome.SUCCESS

    def test_detects_failure_on_failed_status(self, monkeypatch):
        monkeypatch.setattr(deployer.time, "sleep", lambda _s: None)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        statuses = [(RunStatus.FAILED, JobStatus.FAILED)]
        logs = [[_log_event("ValueError: KV cache\n", ts)]]
        api = _make_api(statuses, logs)

        outcome, error_logs = _monitor_run(api, "svc", timeout_secs=60)
        assert outcome is _Outcome.FAILED
        assert "KV cache" in error_logs

    def test_detects_failure_on_fatal_log_pattern(self, monkeypatch):
        monkeypatch.setattr(deployer.time, "sleep", lambda _s: None)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        statuses = [(RunStatus.RUNNING, JobStatus.RUNNING)]
        logs = [[_log_event("Engine core initialization failed\n", ts)]]
        api = _make_api(statuses, logs)

        outcome, error_logs = _monitor_run(api, "svc", timeout_secs=60)
        assert outcome is _Outcome.FAILED
        assert "Engine core initialization failed" in error_logs


def _make_run(run_id: str, submission_id: str, deployment_num: int = 0) -> MagicMock:
    run = MagicMock()
    run._run.id = run_id
    submission = MagicMock()
    submission.id = submission_id
    submission.deployment_num = deployment_num
    run._run.jobs = [MagicMock(job_submissions=[submission])]
    return run


class TestSubmissionToken:
    def test_returns_none_when_run_missing(self):
        api = MagicMock()
        api.runs.get.return_value = None
        assert _submission_token(api, "svc") is None

    def test_changes_when_new_submission(self):
        api = MagicMock()
        token1 = _make_token(api, "run-1", "sub-1", 0)
        token2 = _make_token(api, "run-1", "sub-2", 1)
        assert token1 != token2


def _make_token(api, run_id, submission_id, deployment_num):
    api.runs.get.return_value = _make_run(run_id, submission_id, deployment_num)
    return _submission_token(api, "svc")


class TestSelfHealingLoopDeclineExit:
    def test_exits_without_monitoring_when_user_declines(self, monkeypatch):
        """Declining the plan must not be treated as a deployment failure."""
        api = MagicMock()
        # No run exists before or after apply -> user declined the plan.
        api.runs.get.return_value = None

        # apply_configuration is a no-op (simulates the declined prompt path).
        monkeypatch.setattr(
            deployer.ServiceConfigurator, "apply_configuration", lambda *a, **k: None
        )
        monitor_called = MagicMock()
        monkeypatch.setattr(deployer, "_monitor_run", monitor_called)
        stop_called = MagicMock()
        monkeypatch.setattr(deployer, "_stop_run", stop_called)

        params = EndpointCreateParams(model="meta-llama/Meta-Llama-3.1-8B-Instruct", name="svc")
        command_args = argparse.Namespace(yes=False, verbose=False, force=False, detach=False)
        configuration = MagicMock()
        configuration.name = "svc"

        _run_self_healing_loop(
            api=api,
            configuration=configuration,
            params=params,
            config_path=MagicMock(),
            command_args=command_args,
            configurator_args=argparse.Namespace(),
            skill_path=None,
            max_attempts=3,
            monitor_timeout_secs=60,
        )

        monitor_called.assert_not_called()
        stop_called.assert_not_called()


class TestAttachedApply:
    def test_uses_pre_attach_hook_and_skips_custom_monitor(self, monkeypatch):
        api = MagicMock()
        run = _make_run("run-1", "sub-1", 0)
        api.runs.get.side_effect = [None, run]
        apply_calls = []

        def fake_apply(_self, conf, configuration_path, command_args, configurator_args):
            apply_calls.append(command_args)
            if command_args.pre_attach_hook is not None:
                command_args.pre_attach_hook(conf.name)

        monkeypatch.setattr(deployer.ServiceConfigurator, "apply_configuration", fake_apply)
        monitor_called = MagicMock()
        monkeypatch.setattr(deployer, "_monitor_run", monitor_called)

        params = EndpointCreateParams(model="meta-llama/Meta-Llama-3.1-8B-Instruct", name="svc")
        command_args = argparse.Namespace(yes=False, verbose=False, force=False, detach=False)
        configuration = MagicMock()
        configuration.name = "svc"

        _run_self_healing_loop(
            api=api,
            configuration=configuration,
            params=params,
            config_path=MagicMock(),
            command_args=command_args,
            configurator_args=argparse.Namespace(),
            skill_path=None,
            max_attempts=3,
            monitor_timeout_secs=60,
        )

        assert apply_calls[0].detach is False
        assert apply_calls[0].pre_attach_hook is deployer._print_monitoring_message
        monitor_called.assert_not_called()

    def test_stops_failed_run_before_regenerating_in_attached_mode(self, monkeypatch):
        """A failed attached apply must stop the run before redeploying.

        Otherwise dstack treats the next apply as an in-place rolling update of the
        still-active service and the attached log stream breaks.
        """
        api = MagicMock()
        api.runs.get.return_value = _make_run("run-1", "sub-1", 0)
        call_order = []

        attempts = {"n": 0}

        def fake_apply(_self, conf, configuration_path, command_args, configurator_args):
            attempts["n"] += 1
            call_order.append(f"apply-{attempts['n']}")
            if attempts["n"] == 1:
                raise SystemExit(1)

        monkeypatch.setattr(deployer.ServiceConfigurator, "apply_configuration", fake_apply)
        monkeypatch.setattr(deployer, "_fetch_recent_logs", lambda *a, **k: "boom")
        monkeypatch.setattr(deployer, "_stop_run", lambda *a, **k: call_order.append("stop"))

        new_config = MagicMock()
        new_config.name = "svc"
        monkeypatch.setattr(
            deployer,
            "_regenerate_configuration",
            lambda **k: (call_order.append("regenerate"), (new_config, k["config_path"]))[1],
        )

        params = EndpointCreateParams(model="meta-llama/Meta-Llama-3.1-8B-Instruct", name="svc")
        command_args = argparse.Namespace(yes=False, verbose=False, force=False, detach=False)
        configuration = MagicMock()
        configuration.name = "svc"

        _run_self_healing_loop(
            api=api,
            configuration=configuration,
            params=params,
            config_path=MagicMock(),
            command_args=command_args,
            configurator_args=argparse.Namespace(),
            skill_path=None,
            max_attempts=4,
            monitor_timeout_secs=60,
        )

        assert call_order == ["apply-1", "stop", "regenerate", "apply-2"]


class TestDetachOnInterrupt:
    def test_prompts_and_detaches_when_user_declines_stop(self, monkeypatch):
        api = MagicMock()
        run = MagicMock()
        run.status.is_finished.return_value = False
        api.runs.get.return_value = run
        monkeypatch.setattr(deployer, "confirm_ask", lambda _prompt: False)
        stop_called = MagicMock()
        monkeypatch.setattr(api.client.runs, "stop", stop_called)

        _handle_detach_on_interrupt(api, "my-run", yes=False)

        stop_called.assert_not_called()

    def test_stops_run_when_user_confirms(self, monkeypatch):
        api = MagicMock()
        run = MagicMock()
        run.status.is_finished.return_value = False
        finished_run = MagicMock()
        finished_run.status.is_finished.return_value = True
        api.runs.get.side_effect = [run, finished_run]
        monkeypatch.setattr(deployer, "confirm_ask", lambda _prompt: True)
        monkeypatch.setattr(deployer.time, "sleep", lambda _s: None)

        _handle_detach_on_interrupt(api, "my-run", yes=False)

        api.client.runs.stop.assert_called_once_with(api.project, ["my-run"], False)

    def test_skips_prompt_when_run_already_finished(self, monkeypatch):
        api = MagicMock()
        run = MagicMock()
        run.status.is_finished.return_value = True
        api.runs.get.return_value = run
        confirm_called = MagicMock()
        monkeypatch.setattr(deployer, "confirm_ask", confirm_called)

        _handle_detach_on_interrupt(api, "my-run", yes=False)

        confirm_called.assert_not_called()

    def test_detaches_without_prompt_when_yes_flag_set(self, monkeypatch):
        api = MagicMock()
        run = MagicMock()
        run.status.is_finished.return_value = False
        api.runs.get.return_value = run
        confirm_called = MagicMock()
        monkeypatch.setattr(deployer, "confirm_ask", confirm_called)
        stop_called = MagicMock()
        monkeypatch.setattr(api.client.runs, "stop", stop_called)

        _handle_detach_on_interrupt(api, "my-run", yes=True)

        confirm_called.assert_not_called()
        stop_called.assert_not_called()
