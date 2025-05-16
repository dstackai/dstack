import json
import os
import pydantic
import requests
from dstack._internal.core.errors import ServerError
from dstack._internal.core.models.fleets import FleetSpec
from dstack._internal.core.models.gateways import GatewaySpec
from dstack._internal.core.models.volumes import VolumeSpec
from dstack.plugins import ApplyPolicy, Plugin, RunSpec, get_plugin_logger
from dstack.plugins._models import ApplySpec

logger = get_plugin_logger(__name__)

PLUGIN_SERVICE_URI_ENV_VAR_NAME = "DSTACK_PLUGIN_SERVICE_URI"

class PreApplyPolicy(ApplyPolicy):
    def __init__(self):
        self._plugin_service_uri = os.getenv(PLUGIN_SERVICE_URI_ENV_VAR_NAME)
        if not self._plugin_service_uri:
            logger.error(f"Cannot create policy as {PLUGIN_SERVICE_URI_ENV_VAR_NAME} is not set")
            raise ServerError(f"{PLUGIN_SERVICE_URI_ENV_VAR_NAME} is not set")

    def _call_plugin_service(self, user: str, project: str, spec: ApplySpec, endpoint: str) -> ApplySpec:
        # Make request to plugin service with run params
        params = {
            "user": user,
            "project": project,
            "spec": spec.json()
        }
        response = None
        try:
            response = requests.post(f"{self._plugin_service_uri}/{endpoint}", json=json.dumps(params))
            response.raise_for_status()
            spec_json = json.loads(response.text)
            spec = RunSpec(**spec_json)
        except requests.RequestException as e:
            logger.error("Failed to call plugin service: %s", e)
            if response:
                logger.error(f"Error response from plugin service:\n{response.text}")
            logger.info("Returning original run spec")
            return spec
        except pydantic.ValidationError as e:
            # TODO: check response error status and report if plugin service rejected request as invalid
            logger.exception(f"Plugin service returned invalid response:\n{response.text if response else None}")
            logger.info("Returning original run spec")
            return spec
        logger.info(f"Using RunSpec from plugin service:\n{spec}")
        return spec
    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        return self._call_plugin_service(user, project, spec, '/runs/pre_apply')

    def on_fleet_apply(self, user: str, project: str, spec: FleetSpec) -> FleetSpec:
        return self._call_plugin_service(user, project, spec, '/fleets/pre_apply')
    
    def on_volume_apply(self, user: str, project: str, spec: VolumeSpec) -> VolumeSpec:
        return self._call_plugin_service(user, project, spec, '/volumes/pre_apply')
    
    def on_gateway_apply(self, user: str, project: str, spec: GatewaySpec) -> GatewaySpec:
        return self._call_plugin_service(user, project, spec, '/gateways/pre_apply')

class RESTPlugin(Plugin):
    def get_apply_policies(self) -> list[ApplyPolicy]:
        return [PreApplyPolicy()]
