from datetime import datetime, timezone
from uuid import uuid4

import pytest
from rich.console import Console

import dstack._internal.cli.services.configurators.endpoint as endpoint_configurator_module
from dstack._internal.cli.services.configurators.endpoint import (
    EndpointConfigurator,
    _get_apply_confirm_message,
    _make_endpoint_url_absolute,
    _print_endpoint_plan,
    _print_finished_endpoint_message,
    _print_submitted_endpoint_message,
)
from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.common import ApplyAction
from dstack._internal.core.models.endpoints import (
    Endpoint,
    EndpointConfiguration,
    EndpointPlan,
    EndpointPlanJobOffers,
    EndpointPresetPolicy,
    EndpointProvisioningPlanAgent,
    EndpointProvisioningPlanNone,
    EndpointProvisioningPlanPreset,
    EndpointStatus,
)
from dstack._internal.core.models.resources import ResourcesSpec


def _get_endpoint_plan(
    provisioning_plan: (
        EndpointProvisioningPlanNone
        | EndpointProvisioningPlanPreset
        | EndpointProvisioningPlanAgent
    ),
    current_resource: Endpoint | None = None,
    preset_policy: EndpointPresetPolicy = EndpointPresetPolicy.REUSE_OR_CREATE,
) -> EndpointPlan:
    configuration = EndpointConfiguration(name="qwen-endpoint", model="Qwen/Qwen3-0.6B")
    return EndpointPlan(
        project_name="main",
        user="test-user",
        configuration=configuration,
        configuration_path="endpoint.dstack.yml",
        current_resource=current_resource,
        action=ApplyAction.CREATE if current_resource is None else ApplyAction.UPDATE,
        preset_policy=preset_policy,
        provisioning_plan=provisioning_plan,
    )


def _get_no_provisioning_plan() -> EndpointProvisioningPlanNone:
    return EndpointProvisioningPlanNone(
        reason=(
            "No matching endpoint presets found. "
            "Creating a preset requires the server agent, but "
            "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
        )
    )


def _get_current_endpoint() -> Endpoint:
    configuration = EndpointConfiguration(name="qwen-endpoint", model="Qwen/Qwen3-0.6B")
    return Endpoint(
        id=uuid4(),
        name="qwen-endpoint",
        project_name="main",
        user="test-user",
        configuration=configuration,
        created_at=datetime.now(timezone.utc),
        last_processed_at=datetime.now(timezone.utc),
        status=EndpointStatus.RUNNING,
    )


def _get_failed_endpoint() -> Endpoint:
    endpoint = _get_current_endpoint()
    endpoint.status = EndpointStatus.FAILED
    endpoint.status_message = (
        "Preset policy create requires the server agent, but "
        "DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
    )
    return endpoint


def _patch_console(monkeypatch: pytest.MonkeyPatch) -> Console:
    console = Console(record=True, force_terminal=False, color_system=None, width=120)
    monkeypatch.setattr(endpoint_configurator_module, "console", console)
    return console


class TestPrintEndpointPlan:
    def test_prints_stable_properties_for_missing_provisioning_path(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        console = _patch_console(monkeypatch)
        plan = _get_endpoint_plan(_get_no_provisioning_plan())

        _print_endpoint_plan(plan)

        output = console.export_text()
        assert "Project        main" in output
        assert "Endpoint" not in output
        assert "Resources" not in output
        assert "Spot policy    auto" in output
        assert "Max price      off" in output
        assert "Preset policy  reuse-or-create" in output
        assert "No matching endpoint presets found" in output
        assert "Creating a preset requires the server agent" in output
        assert "Model" not in output
        assert "Action" not in output
        assert "Provisioning" not in output

    def test_prints_preset_without_resources_property(self, monkeypatch: pytest.MonkeyPatch):
        console = _patch_console(monkeypatch)
        resources = ResourcesSpec.parse_obj({"gpu": "16GB", "disk": "60GB"})
        plan = _get_endpoint_plan(
            EndpointProvisioningPlanPreset(
                preset_model="Qwen/Qwen3-0.6B",
                recipe_id="vllm-a40",
                service_name="qwen-endpoint-serving",
                job_offers=[
                    EndpointPlanJobOffers(
                        replica_group="0",
                        resources=resources,
                        spot=False,
                        max_price=0.5,
                        offers=[],
                        total_offers=0,
                        max_offer_price=None,
                    )
                ],
            )
        )

        _print_endpoint_plan(plan)

        output = console.export_text()
        assert "Resources" not in output
        assert "Preset         Qwen/Qwen3-0.6B" in output
        assert "Recipe         vllm-a40" in output

    def test_prints_agent_reason_when_preset_has_no_offers(self, monkeypatch: pytest.MonkeyPatch):
        console = _patch_console(monkeypatch)
        plan = _get_endpoint_plan(
            EndpointProvisioningPlanAgent(
                agent_model="test-agent",
                reason="Endpoint preset qwen matched but has no available offers.",
            )
        )

        _print_endpoint_plan(plan)

        output = console.export_text()
        assert "Preset policy  reuse-or-create" in output
        assert "Endpoint preset qwen matched but has no available offers." in output
        assert "Agent" not in output


class TestPrintSubmittedEndpointMessage:
    def test_prints_generic_detach_message(self, monkeypatch: pytest.MonkeyPatch):
        console = _patch_console(monkeypatch)

        _print_submitted_endpoint_message(_get_current_endpoint())

        output = console.export_text()
        assert "Endpoint qwen-endpoint submitted, detaching..." in output
        assert "without a provisioning path" not in output


class TestPrintFinishedEndpointMessage:
    def test_prints_running_url(self, monkeypatch: pytest.MonkeyPatch):
        console = _patch_console(monkeypatch)
        endpoint = _get_current_endpoint()
        endpoint.url = "/proxy/services/main/qwen-endpoint/v1"

        _print_finished_endpoint_message(endpoint)

        output = console.export_text()
        assert "/proxy/services/main/qwen-endpoint/v1" in output

    def test_makes_relative_url_absolute(self):
        endpoint = _get_current_endpoint()
        endpoint.url = "/proxy/services/main/qwen-endpoint/v1"

        _make_endpoint_url_absolute(endpoint, "http://127.0.0.1:8000")

        assert endpoint.url == "http://127.0.0.1:8000/proxy/services/main/qwen-endpoint/v1"

    def test_prints_failed_message_without_logs_hint(self, monkeypatch: pytest.MonkeyPatch):
        console = _patch_console(monkeypatch)

        _print_finished_endpoint_message(_get_failed_endpoint())

        output = console.export_text()
        assert "DSTACK_AGENT_ANTHROPIC_API_KEY" in output
        assert "dstack logs" not in output


class TestGetApplyConfirmMessage:
    def test_asks_to_create_without_provisioning_path(self):
        plan = _get_endpoint_plan(_get_no_provisioning_plan())

        assert _get_apply_confirm_message(plan) == "Create the endpoint?"

    def test_asks_to_override_without_provisioning_path(self):
        plan = _get_endpoint_plan(
            _get_no_provisioning_plan(),
            current_resource=_get_current_endpoint(),
        )

        assert (
            _get_apply_confirm_message(plan)
            == "Stop and override the endpoint [code]qwen-endpoint[/]?"
        )

    def test_asks_to_create_when_existing_endpoint_is_terminal(self):
        plan = _get_endpoint_plan(
            _get_no_provisioning_plan(),
            current_resource=_get_failed_endpoint(),
        )

        assert _get_apply_confirm_message(plan) == "Create the endpoint?"

    def test_asks_to_override_same_name_run(self):
        plan = _get_endpoint_plan(EndpointProvisioningPlanAgent(agent_model="test-agent"))

        assert (
            _get_apply_confirm_message(plan, stop_run_name="qwen-endpoint")
            == "Stop and override the run [code]qwen-endpoint[/]?"
        )


class TestEndpointConfigurator:
    def test_delete_configuration_is_not_supported(self):
        configurator = EndpointConfigurator.__new__(EndpointConfigurator)
        conf = EndpointConfiguration(name="qwen-endpoint", model="Qwen/Qwen3-0.6B")

        with pytest.raises(ConfigurationError, match="dstack endpoint stop"):
            configurator.delete_configuration(conf, "endpoint.dstack.yml", command_args=None)
