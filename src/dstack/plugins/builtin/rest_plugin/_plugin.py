import json
import os
from typing import Dict, Optional, Type

import requests
from pydantic import ValidationError

from dstack._internal.core.compatibility.fleets import get_fleet_spec_excludes
from dstack._internal.core.compatibility.gateways import get_gateway_spec_excludes
from dstack._internal.core.compatibility.runs import get_run_spec_excludes
from dstack._internal.core.compatibility.volumes import get_volume_spec_excludes
from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.volumes import VolumeSpec
from dstack.plugins import ApplyPolicy, ApplySpec, Plugin, RunSpec, get_plugin_logger
from dstack.plugins.builtin.rest_plugin import (
    FleetSpecRequest,
    FleetSpecResponse,
    GatewaySpecRequest,
    GatewaySpecResponse,
    RunSpecRequest,
    RunSpecResponse,
    SpecApplyRequest,
    SpecApplyResponse,
    VolumeSpecRequest,
    VolumeSpecResponse,
)

logger = get_plugin_logger(__name__)

PLUGIN_SERVICE_URI_ENV_VAR_NAME = "DSTACK_PLUGIN_SERVICE_URI"
PLUGIN_REQUEST_TIMEOUT_SEC = 8


class CustomApplyPolicy(ApplyPolicy):
    def __init__(self):
        self._plugin_service_uri = os.getenv(PLUGIN_SERVICE_URI_ENV_VAR_NAME)
        logger.info(f"Found plugin service at {self._plugin_service_uri}")
        if not self._plugin_service_uri:
            logger.error(
                f"Cannot create policy because {PLUGIN_SERVICE_URI_ENV_VAR_NAME} is not set"
            )
            raise ServerClientError(f"{PLUGIN_SERVICE_URI_ENV_VAR_NAME} is not set")

    def _check_request_rejected(self, response: SpecApplyResponse):
        if response.error is not None:
            logger.error(f"Plugin service rejected apply request: {response.error}")
            raise ServerClientError(f"Apply request rejected: {response.error}")

    def _call_plugin_service(
        self,
        spec_request: SpecApplyRequest,
        endpoint: str,
        excludes: Optional[Dict],
    ) -> ApplySpec:
        response = None
        try:
            response = requests.post(
                f"{self._plugin_service_uri}{endpoint}",
                json=spec_request.dict(exclude={"spec": excludes}),
                headers={"accept": "application/json", "Content-Type": "application/json"},
                timeout=PLUGIN_REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()
            spec_json = json.loads(response.text)
            return spec_json
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Could not connect to plugin service at {self._plugin_service_uri}: %s", e
            )
            raise ServerClientError(
                f"Could not connect to plugin service at {self._plugin_service_uri}"
            )
        except requests.RequestException as e:
            logger.error("Request to the plugin service failed: %s", e)
            raise ServerClientError("Request to the plugin service failed")

    def _on_apply(
        self,
        request_cls: Type[SpecApplyRequest],
        response_cls: Type[SpecApplyResponse],
        endpoint: str,
        user: str,
        project: str,
        spec: ApplySpec,
        excludes: Optional[Dict] = None,
    ) -> ApplySpec:
        spec_json = None
        try:
            spec_request = request_cls(user=user, project=project, spec=spec)
            spec_json = self._call_plugin_service(spec_request, endpoint, excludes)
            response = response_cls(**spec_json)
            self._check_request_rejected(response)
            return response.spec
        except ValidationError:
            logger.error(f"Plugin service returned invalid response:\n{spec_json}")
            raise ServerClientError("Plugin service returned an invalid response")

    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        return self._on_apply(
            RunSpecRequest,
            RunSpecResponse,
            "/apply_policies/on_run_apply",
            user,
            project,
            spec,
            excludes=get_run_spec_excludes(spec),
        )

    def on_fleet_apply(self, user: str, project: str, spec: FleetSpec) -> FleetSpec:
        return self._on_apply(
            FleetSpecRequest,
            FleetSpecResponse,
            "/apply_policies/on_fleet_apply",
            user,
            project,
            spec,
            excludes=get_fleet_spec_excludes(spec),
        )

    def on_volume_apply(self, user: str, project: str, spec: VolumeSpec) -> VolumeSpec:
        return self._on_apply(
            VolumeSpecRequest,
            VolumeSpecResponse,
            "/apply_policies/on_volume_apply",
            user,
            project,
            spec,
            excludes=get_volume_spec_excludes(spec),
        )

    def on_gateway_apply(self, user: str, project: str, spec: GatewaySpec) -> GatewaySpec:
        return self._on_apply(
            GatewaySpecRequest,
            GatewaySpecResponse,
            "/apply_policies/on_gateway_apply",
            user,
            project,
            spec,
            excludes=get_gateway_spec_excludes(spec),
        )


class RESTPlugin(Plugin):
    def get_apply_policies(self) -> list[ApplyPolicy]:
        return [CustomApplyPolicy()]
