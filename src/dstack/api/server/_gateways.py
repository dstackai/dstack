from typing import List

from pydantic import parse_obj_as

from dstack._internal.core.compatibility.gateways import get_create_gateway_excludes
from dstack._internal.core.models.gateways import Gateway, GatewayConfiguration
from dstack._internal.server.schemas.gateways import (
    CreateGatewayRequest,
    DeleteGatewaysRequest,
    GetGatewayRequest,
    SetDefaultGatewayRequest,
    SetWildcardDomainRequest,
)
from dstack.api.server._group import APIClientGroup


class GatewaysAPIClient(APIClientGroup):
    def list(self, project_name: str) -> List[Gateway]:
        resp = self._request(f"/api/project/{project_name}/gateways/list")
        return parse_obj_as(List[Gateway.__response__], resp.json())

    def get(self, project_name: str, gateway_name: str) -> Gateway:
        body = GetGatewayRequest(name=gateway_name)
        resp = self._request(f"/api/project/{project_name}/gateways/get", body=body.json())
        return parse_obj_as(Gateway.__response__, resp.json())

    def create(
        self,
        project_name: str,
        configuration: GatewayConfiguration,
    ) -> Gateway:
        body = CreateGatewayRequest(configuration=configuration)
        resp = self._request(
            f"/api/project/{project_name}/gateways/create",
            body=body.json(exclude=get_create_gateway_excludes(configuration)),
        )
        return parse_obj_as(Gateway.__response__, resp.json())

    def delete(self, project_name: str, gateways_names: List[str]) -> None:
        body = DeleteGatewaysRequest(names=gateways_names)
        self._request(f"/api/project/{project_name}/gateways/delete", body=body.json())

    def set_default(self, project_name: str, gateway_name: str) -> None:
        body = SetDefaultGatewayRequest(name=gateway_name)
        self._request(f"/api/project/{project_name}/gateways/set_default", body=body.json())

    def set_wildcard_domain(
        self, project_name: str, gateway_name: str, wildcard_domain: str
    ) -> Gateway:
        body = SetWildcardDomainRequest(name=gateway_name, wildcard_domain=wildcard_domain)
        resp = self._request(
            f"/api/project/{project_name}/gateways/set_wildcard_domain", body=body.json()
        )
        return parse_obj_as(Gateway.__response__, resp.json())
