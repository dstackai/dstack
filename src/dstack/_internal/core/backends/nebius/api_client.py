import time
from typing import Dict, List, Optional

import jwt
import requests

from dstack._internal.core.backends.nebius.types import (
    ClientError,
    ConflictError,
    ForbiddenError,
    NebiusError,
    NotFoundError,
    ResourcesSpec,
    ServiceAccount,
)
from dstack._internal.utils.logging import get_logger

logger = get_logger("nebius")
API_URL = "api.ai.nebius.cloud"
REQUEST_TIMEOUT = 15


class NebiusAPIClient:
    # Reference: https://nebius.ai/docs/api-design-guide/
    def __init__(self, service_account: ServiceAccount):
        self.service_account = service_account
        self.s = requests.Session()
        self.expires_at = 0

    def get_token(self):
        now = int(time.time())
        if now + 60 < self.expires_at:
            return
        logger.debug("Refreshing IAM token")
        expires_at = now + 3600
        payload = {
            "aud": self.url("iam", "/tokens"),
            "iss": self.service_account["service_account_id"],
            "iat": now,
            "exp": expires_at,
        }
        jwt_token = jwt.encode(
            payload,
            self.service_account["private_key"],
            algorithm="PS256",
            headers={"kid": self.service_account["id"]},
        )

        resp = requests.post(payload["aud"], json={"jwt": jwt_token}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        iam_token = resp.json()["iamToken"]
        self.s.headers["Authorization"] = f"Bearer {iam_token}"
        self.expires_at = expires_at

    def compute_zones_list(self) -> List[dict]:
        logger.debug("Fetching compute zones")
        self.get_token()
        resp = self.s.get(self.url("compute", "/zones"), timeout=REQUEST_TIMEOUT)
        self.raise_for_status(resp)
        return resp.json()["zones"]

    def resource_manager_folders_create(self, cloud_id: str, name: str, **kwargs) -> dict:
        logger.debug("Creating folder %s", name)
        self.get_token()
        resp = self.s.post(
            self.url("resource-manager", "/folders"),
            json=omit_none(
                cloudId=cloud_id,
                name=name,
                **kwargs,
            ),
            timeout=REQUEST_TIMEOUT,
        )
        self.raise_for_status(resp)
        return resp.json()

    def vpc_networks_create(self, folder_id: str, name: str, **kwargs) -> dict:
        logger.debug("Creating network %s in %s", name, folder_id)
        self.get_token()
        resp = self.s.post(
            self.url("vpc", "/networks"),
            json=omit_none(
                folderId=folder_id,
                name=name,
                **kwargs,
            ),
            timeout=REQUEST_TIMEOUT,
        )
        self.raise_for_status(resp)
        return resp.json()

    def vpc_networks_list(self, folder_id: str, filter: Optional[str] = None) -> List[dict]:
        logger.debug("Fetching networks in %s", folder_id)
        return self.list(
            "vpc",
            "networks",
            params=dict(
                folderId=folder_id,
                filter=filter,
            ),
        )

    def vpc_subnets_create(
        self,
        folder_id: str,
        name: str,
        network_id: str,
        zone: str,
        cird_blocks: List[str],
        **kwargs,
    ) -> dict:
        logger.debug("Creating subnet %s in %s", name, network_id)
        self.get_token()
        resp = self.s.post(
            self.url("vpc", "/subnets"),
            json=omit_none(
                folderId=folder_id,
                name=name,
                networkId=network_id,
                zoneId=zone,
                v4CidrBlocks=cird_blocks,
                **kwargs,
            ),
            timeout=REQUEST_TIMEOUT,
        )
        self.raise_for_status(resp)
        return resp.json()

    def vpc_subnets_list(self, folder_id: str, filter: Optional[str] = None) -> List[dict]:
        logger.debug("Fetching subnets in %s", folder_id)
        return self.list(
            "vpc",
            "subnets",
            params=dict(
                folderId=folder_id,
                filter=filter,
            ),
        )

    def vpc_security_groups_create(
        self, folder_id: str, name: str, network_id: str, rule_specs: List[dict], **kwargs
    ) -> dict:
        logger.debug("Creating security group %s in %s", name, folder_id)
        self.get_token()
        resp = self.s.post(
            self.url("vpc", "/securityGroups"),
            json=omit_none(
                folderId=folder_id,
                name=name,
                networkId=network_id,
                ruleSpecs=rule_specs,
                **kwargs,
            ),
            timeout=REQUEST_TIMEOUT,
        )
        self.raise_for_status(resp)
        return resp.json()

    def vpc_security_groups_list(self, folder_id: str, filter: Optional[str] = None) -> List[dict]:
        logger.debug("Fetching security groups in %s", folder_id)
        return self.list(
            "vpc",
            "securityGroups",
            params=dict(
                folderId=folder_id,
                filter=filter,
            ),
        )

    def vpc_security_groups_delete(self, security_group_id: str):
        logger.debug("Deleting security group %s", security_group_id)
        self.get_token()
        resp = self.s.delete(
            self.url("vpc", f"/securityGroups/{security_group_id}"), timeout=REQUEST_TIMEOUT
        )
        self.raise_for_status(resp)

    def compute_instances_create(
        self,
        folder_id: str,
        name: str,
        zone_id: str,
        platform_id: str,
        resources_spec: ResourcesSpec,
        metadata: Optional[Dict[str, str]],
        disk_size_gb: int,
        image_id: str,
        subnet_id: str,
        security_group_ids: List[str],
        **kwargs,
    ) -> dict:
        # Reference: https://nebius.ai/docs/api-design-guide/compute/v1/api-ref/Instance/create
        logger.debug("Creating instance %s (%s) in %s", name, platform_id, folder_id)
        self.get_token()
        resp = self.s.post(
            self.url("compute", "/instances"),
            json=omit_none(
                folderId=folder_id,
                name=name,
                zoneId=zone_id,
                platformId=platform_id,
                resourcesSpec=resources_spec,
                metadata=metadata,
                boot_disk_spec=dict(
                    autoDelete=True,
                    diskSpec=dict(
                        typeId="network-ssd",
                        size=disk_size_gb * 1024 * 1024 * 1024,
                        imageId=image_id,
                    ),
                ),
                networkInterfaceSpecs=[
                    dict(
                        subnetId=subnet_id,
                        primaryV4AddressSpec=dict(
                            oneToOneNatSpec=dict(
                                ipVersion="IPV4",
                            ),
                        ),
                        securityGroupIds=security_group_ids,
                    )
                ],
                **kwargs,
            ),
            timeout=REQUEST_TIMEOUT,
        )
        self.raise_for_status(resp)
        return resp.json()

    def compute_instances_list(
        self, folder_id: str, filter: Optional[str] = None, order_by: Optional[str] = None
    ) -> List[dict]:
        logger.debug("Fetching instances in %s", folder_id)
        return self.list(
            "compute",
            "instances",
            params=dict(
                folderId=folder_id,
                filter=filter,
                orderBy=order_by,
            ),
        )

    def compute_instances_delete(self, instance_id: str):
        logger.debug("Deleting instance %s", instance_id)
        self.get_token()
        resp = self.s.delete(
            self.url("compute", f"/instances/{instance_id}"), timeout=REQUEST_TIMEOUT
        )
        self.raise_for_status(resp)

    def compute_instances_get(self, instance_id: str, full: bool = False) -> dict:
        logger.debug("Fetching instance %s", instance_id)
        self.get_token()
        resp = self.s.get(
            self.url("compute", f"/instances/{instance_id}"),
            params=dict(
                view="FULL" if full else "BASIC",
            ),
            timeout=REQUEST_TIMEOUT,
        )
        self.raise_for_status(resp)
        return resp.json()

    def compute_images_list(
        self, folder_id: str, filter: Optional[str] = None, order_by: Optional[str] = None
    ):
        logger.debug("Fetching images in %s", folder_id)
        return self.list(
            "compute",
            "images",
            params=dict(
                folderId=folder_id,
                filter=filter,
                orderBy=order_by,
            ),
        )

    def list(self, service: str, resource: str, params: dict, page_size: int = 1000) -> List[dict]:
        page_token = None
        output = []
        while True:
            self.get_token()
            resp = self.s.get(
                self.url(service, f"/{resource}"),
                params=omit_none(
                    pageSize=page_size,
                    pageToken=page_token,
                    **params,
                ),
                timeout=REQUEST_TIMEOUT,
            )
            self.raise_for_status(resp)
            data = resp.json()
            output += data.get(resource, [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return output

    def url(self, service: str, path: str, version="v1") -> str:
        return f"https://{service}.{API_URL.rstrip('/')}/{service}/{version}/{path.lstrip('/')}"

    def raise_for_status(self, resp: requests.Response):
        if resp.status_code == 400:
            raise NebiusError(resp.text)
        if resp.status_code == 401:
            raise ClientError(resp.text)
        if resp.status_code == 403:
            raise ForbiddenError(resp.text)
        if resp.status_code == 404:
            raise NotFoundError(resp.text)
        if resp.status_code == 409:
            raise ConflictError(resp.text)
        resp.raise_for_status()


def omit_none(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}
