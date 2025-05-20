import json
import os
from typing import Generic, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.volumes import VolumeSpec
from dstack.plugins import ApplyPolicy, Plugin, RunSpec, get_plugin_logger
from dstack.plugins._models import ApplySpec

logger = get_plugin_logger(__name__)

PLUGIN_SERVICE_URI_ENV_VAR_NAME = "DSTACK_PLUGIN_SERVICE_URI"
PLUGIN_REQUEST_TIMEOUT = 8  # in seconds

SpecType = TypeVar("SpecType", RunSpec, FleetSpec, VolumeSpec, GatewaySpec)


class SpecRequest(BaseModel, Generic[SpecType]):
    user: str
    project: str
    spec: SpecType


RunSpecRequest = SpecRequest[RunSpec]
FleetSpecRequest = SpecRequest[FleetSpec]
VolumeSpecRequest = SpecRequest[VolumeSpec]
GatewaySpecRequest = SpecRequest[GatewaySpec]


class CustomApplyPolicy(ApplyPolicy):
    def __init__(self):
        self._plugin_service_uri = os.getenv(PLUGIN_SERVICE_URI_ENV_VAR_NAME)
        logger.info(f"Found plugin service at {self._plugin_service_uri}")
        if not self._plugin_service_uri:
            logger.error(
                f"Cannot create policy because {PLUGIN_SERVICE_URI_ENV_VAR_NAME} is not set"
            )
            raise ServerClientError(f"{PLUGIN_SERVICE_URI_ENV_VAR_NAME} is not set")

    def _call_plugin_service(self, spec_request: SpecRequest, endpoint: str) -> ApplySpec:
        response = None
        try:
            response = requests.post(
                f"{self._plugin_service_uri}{endpoint}",
                json=spec_request.dict(),
                headers={"accept": "application/json", "Content-Type": "application/json"},
                timeout=PLUGIN_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            spec_json = json.loads(response.text)
            return spec_json
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Could not connect to plugin service at {self._plugin_service_uri}: %s", e
            )
            raise e
        except requests.RequestException as e:
            logger.error("Request to the plugin service failed: %s", e)
            if response:
                logger.error(f"Error response from plugin service:\n{response.text}")
            raise e
        except ValidationError as e:
            # Received 200 code but response body is invalid
            logger.exception(
                f"Plugin service returned invalid response:\n{response.text if response else None}"
            )
            raise e

    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        spec_request = RunSpecRequest(user=user, project=project, spec=spec)
        spec_json = self._call_plugin_service(spec_request, "/apply_policies/on_run_apply")
        return RunSpec(**spec_json)

    def on_fleet_apply(self, user: str, project: str, spec: FleetSpec) -> FleetSpec:
        spec_request = FleetSpecRequest(user=user, project=project, spec=spec)
        spec_json = self._call_plugin_service(spec_request, "/apply_policies/on_fleet_apply")
        return FleetSpec(**spec_json)

    def on_volume_apply(self, user: str, project: str, spec: VolumeSpec) -> VolumeSpec:
        spec_request = VolumeSpecRequest(user=user, project=project, spec=spec)
        spec_json = self._call_plugin_service(spec_request, "/apply_policies/on_volume_apply")
        return VolumeSpec(**spec_json)

    def on_gateway_apply(self, user: str, project: str, spec: GatewaySpec) -> GatewaySpec:
        spec_request = GatewaySpecRequest(user=user, project=project, spec=spec)
        spec_json = self._call_plugin_service(spec_request, "/apply_policies/on_gateway_apply")
        return GatewaySpec(**spec_json)


class RESTPlugin(Plugin):
    def get_apply_policies(self) -> list[ApplyPolicy]:
        return [CustomApplyPolicy()]
