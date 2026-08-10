from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from dstack._internal.cli.services.configurators import run as run_configurator
from dstack._internal.cli.services.configurators.run import (
    ApplyPlanOutcome,
    ApplyPlanResult,
    BaseRunConfigurator,
    RunApplyFence,
)
from dstack._internal.core.errors import CLIError
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.runs import RunStatus


def _plan(*, action: ApplyAction, current_resource, run_name: str | None = "dev-run"):
    run_spec = SimpleNamespace(run_name=run_name)
    return SimpleNamespace(
        user="owner",
        run_spec=run_spec,
        effective_run_spec=run_spec,
        get_effective_run_spec=lambda: run_spec,
        job_plans=[SimpleNamespace(offers=[object()])],
        current_resource=current_resource,
        action=action,
    )


def _current_resource(*, status: RunStatus = RunStatus.RUNNING, user: str = "owner"):
    return SimpleNamespace(
        id=uuid4(),
        deployment_num=4,
        status=status,
        user=user,
        run_spec=SimpleNamespace(run_name="dev-run"),
    )


def _applied_run(*, deployment_num: int = 5, user: str = "owner"):
    run = Mock()
    run.name = "dev-run"
    run._run = SimpleNamespace(
        id=uuid4(),
        deployment_num=deployment_num,
        user=user,
    )
    return run


def _args(**overrides):
    values = {
        "yes": True,
        "force": False,
        "no_recreate": True,
        "detach": True,
        "verbose": False,
    }
    values.update(overrides)
    return Namespace(**values)


def _configurator_args():
    return Namespace(max_offers=3)


@pytest.fixture(autouse=True)
def quiet_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_configurator, "print_run_plan", Mock())


class TestApplyPlanNoRecreate:
    @pytest.mark.parametrize(
        "status",
        [RunStatus.SUBMITTED, RunStatus.PROVISIONING, RunStatus.RUNNING],
    )
    def test_treats_unchanged_safe_active_run_as_noop(
        self,
        status: RunStatus,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        current = _current_resource(status=status)
        plan = _plan(action=ApplyAction.UPDATE, current_resource=current)
        api = Mock()
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: None)

        outcome = BaseRunConfigurator(api).apply_plan(
            run_plan=plan,
            repo=Mock(),
            command_args=_args(detach=False),
            configurator_args=_configurator_args(),
        )

        assert outcome == ApplyPlanOutcome(
            result=ApplyPlanResult.NOOP,
            fence=RunApplyFence(
                run_id=str(current.id),
                deployment_num=current.deployment_num,
                user=current.user,
            ),
        )
        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_not_called()
        assert "already up to date" in capsys.readouterr().out

    @pytest.mark.parametrize("status", [RunStatus.PENDING, RunStatus.TERMINATING])
    def test_refuses_unsafe_active_status_even_when_unchanged(
        self,
        status: RunStatus,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        current = _current_resource(status=status)
        plan = _plan(action=ApplyAction.UPDATE, current_resource=current)
        api = Mock()
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: None)

        with pytest.raises(CLIError, match="Refusing to change active run"):
            BaseRunConfigurator(api).apply_plan(
                run_plan=plan,
                repo=Mock(),
                command_args=_args(),
                configurator_args=_configurator_args(),
            )

        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_not_called()

    def test_refuses_active_run_owned_by_another_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        current = _current_resource(user="another-user")
        plan = _plan(action=ApplyAction.UPDATE, current_resource=current)
        api = Mock()
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: None)

        with pytest.raises(CLIError, match="owned by another user"):
            BaseRunConfigurator(api).apply_plan(
                run_plan=plan,
                repo=Mock(),
                command_args=_args(),
                configurator_args=_configurator_args(),
            )

        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_not_called()

    def test_refuses_in_place_update(self, monkeypatch: pytest.MonkeyPatch) -> None:
        current = _current_resource()
        plan = _plan(action=ApplyAction.UPDATE, current_resource=current)
        api = Mock()
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: "safe diff")

        with pytest.raises(CLIError, match="Refusing to change active run"):
            BaseRunConfigurator(api).apply_plan(
                run_plan=plan,
                repo=Mock(),
                command_args=_args(),
                configurator_args=_configurator_args(),
            )

        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_not_called()

    @pytest.mark.parametrize("diff", [None, "unsafe diff"])
    def test_refuses_recreation_action(
        self,
        diff: str | None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        current = _current_resource()
        plan = _plan(action=ApplyAction.CREATE, current_resource=current)
        api = Mock()
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: diff)

        with pytest.raises(CLIError, match="Refusing to change active run"):
            BaseRunConfigurator(api).apply_plan(
                run_plan=plan,
                repo=Mock(),
                command_args=_args(),
                configurator_args=_configurator_args(),
            )

        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_not_called()

    def test_submits_when_run_is_absent(self) -> None:
        plan = _plan(action=ApplyAction.CREATE, current_resource=None)
        api = Mock()
        applied = _applied_run()
        api.runs.apply_plan.return_value = applied

        outcome = BaseRunConfigurator(api).apply_plan(
            run_plan=plan,
            repo=Mock(),
            command_args=_args(),
            configurator_args=_configurator_args(),
        )

        assert outcome == ApplyPlanOutcome(
            result=ApplyPlanResult.SUBMITTED,
            fence=RunApplyFence(
                run_id=str(applied._run.id),
                deployment_num=applied._run.deployment_num,
                user=applied._run.user,
            ),
        )
        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_called_once()

    def test_submits_when_previous_run_is_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        current = _current_resource(status=RunStatus.TERMINATED)
        plan = _plan(action=ApplyAction.CREATE, current_resource=current)
        api = Mock()
        applied = _applied_run(deployment_num=current.deployment_num + 1)
        api.runs.apply_plan.return_value = applied
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: "new spec")

        outcome = BaseRunConfigurator(api).apply_plan(
            run_plan=plan,
            repo=Mock(),
            command_args=_args(),
            configurator_args=_configurator_args(),
        )

        assert outcome == ApplyPlanOutcome(
            result=ApplyPlanResult.SUBMITTED,
            fence=RunApplyFence(
                run_id=str(applied._run.id),
                deployment_num=applied._run.deployment_num,
                user=applied._run.user,
            ),
        )
        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_called_once()

    def test_rejects_unnamed_run(self) -> None:
        plan = _plan(action=ApplyAction.CREATE, current_resource=None, run_name=None)
        api = Mock()

        with pytest.raises(CLIError, match="requires a named run"):
            BaseRunConfigurator(api).apply_plan(
                run_plan=plan,
                repo=Mock(),
                command_args=_args(),
                configurator_args=_configurator_args(),
            )

        api.runs.apply_plan.assert_not_called()


class TestApplyPlanOutcome:
    def test_reports_cancelled_without_applying(self, monkeypatch: pytest.MonkeyPatch) -> None:
        plan = _plan(action=ApplyAction.CREATE, current_resource=None)
        api = Mock()
        monkeypatch.setattr(run_configurator, "confirm_ask", lambda *_: False)

        outcome = BaseRunConfigurator(api).apply_plan(
            run_plan=plan,
            repo=Mock(),
            command_args=_args(yes=False),
            configurator_args=_configurator_args(),
        )

        assert outcome == ApplyPlanOutcome(result=ApplyPlanResult.CANCELLED)
        api.runs.apply_plan.assert_not_called()

    def test_reports_normal_unchanged_apply_as_noop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        current = _current_resource()
        plan = _plan(action=ApplyAction.UPDATE, current_resource=current)
        api = Mock()
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: None)

        outcome = BaseRunConfigurator(api).apply_plan(
            run_plan=plan,
            repo=Mock(),
            command_args=_args(no_recreate=False),
            configurator_args=_configurator_args(),
        )

        assert outcome == ApplyPlanOutcome(
            result=ApplyPlanResult.NOOP,
            fence=RunApplyFence(
                run_id=str(current.id),
                deployment_num=current.deployment_num,
                user=current.user,
            ),
        )
        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_not_called()

    def test_submitted_fence_comes_from_applied_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        current = _current_resource()
        plan = _plan(action=ApplyAction.UPDATE, current_resource=current)
        api = Mock()
        applied = _applied_run(deployment_num=current.deployment_num + 1)
        api.runs.apply_plan.return_value = applied
        monkeypatch.setattr(run_configurator, "render_run_spec_diff", lambda *_: "safe diff")

        outcome = BaseRunConfigurator(api).apply_plan(
            run_plan=plan,
            repo=Mock(),
            command_args=_args(no_recreate=False),
            configurator_args=_configurator_args(),
        )

        assert outcome == ApplyPlanOutcome(
            result=ApplyPlanResult.SUBMITTED,
            fence=RunApplyFence(
                run_id=str(applied._run.id),
                deployment_num=applied._run.deployment_num,
                user=applied._run.user,
            ),
        )
        assert outcome.fence != RunApplyFence(
            run_id=str(current.id),
            deployment_num=current.deployment_num,
            user=current.user,
        )
        api.client.runs.stop.assert_not_called()
        api.runs.apply_plan.assert_called_once()
