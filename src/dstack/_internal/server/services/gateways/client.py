import asyncio
import uuid
from typing import Optional

import httpx
from pydantic import TypeAdapter

from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.common import validate_json_extra_ignore
from dstack._internal.core.models.configurations import RateLimit, ServiceConfiguration
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import JobSpec, JobSubmission, get_service_port
from dstack._internal.proxy.gateway.schemas.config import ConfigRequest
from dstack._internal.proxy.gateway.schemas.metering import (
    CollectMeteringRequest,
    CollectMeteringResponse,
    MeteringBatch,
)
from dstack._internal.proxy.gateway.schemas.registry import (
    ImportListItem,
    ImportListResponse,
    RegisterImportRequest,
    ReplicaProxyJumpKeyUpdate,
    UnregisterImportRequest,
    UpdateReplicaProxyJumpKeysResponse,
)
from dstack._internal.proxy.gateway.schemas.services import ServiceListItem, ServiceListResponse
from dstack._internal.proxy.gateway.schemas.state import StateSummaryResponse
from dstack._internal.proxy.gateway.schemas.stats import ServiceStats


class GatewayClient:
    def __init__(self, uds: Optional[str] = None, port: Optional[int] = None):
        if uds is None and port is None:
            raise ValueError("Either uds or port should be specified")
        if uds is not None and port is not None:
            raise ValueError("Either uds or port should be specified, not both")

        # Shows that the gateway's HTTP server has started. Should become True
        # in info() during gateway setup. If setup fails, it
        # should become True after any other successful request.
        self.is_server_ready = False

        self.base_url = "http://gateway" if uds else f"http://localhost:{port}"
        # We set large timeout because service registration can take time.
        # Consider making gateway API async to avoid long-running requests.
        self._client = AsyncClientWrapper(
            transport=httpx.AsyncHTTPTransport(uds=uds) if uds else None, timeout=120
        )

    async def register_service(
        self,
        project: str,
        run_id: uuid.UUID,
        run_name: str,
        domain: str,
        service_https: bool,
        gateway_https: bool,
        auth: bool,
        client_max_body_size: int,
        read_timeout: int,
        options: dict,
        rate_limits: list[RateLimit],
        ssh_private_key: str,
        has_router_replica: bool = False,
    ):
        if "openai" in options:
            entrypoint = get_gateway_endpoint_domain(domain)
            await self.register_openai_entrypoint(project, entrypoint, gateway_https, read_timeout)

        payload = {
            "id": run_id.hex,
            "run_name": run_name,
            "domain": domain,
            "https": service_https,
            "auth": auth,
            "client_max_body_size": client_max_body_size,
            "read_timeout": read_timeout,
            "options": options,
            "rate_limits": [limit.model_dump() for limit in rate_limits],
            "ssh_private_key": ssh_private_key,
            "has_router_replica": has_router_replica,
        }
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/services/register"), json=payload
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def unregister_service(self, project: str, run_name: str):
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/services/{run_name}/unregister")
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def register_replica(
        self,
        project: str,
        run_name: str,
        configuration: ServiceConfiguration,
        job_spec: JobSpec,
        job_submission: JobSubmission,
        instance_project_ssh_private_key: Optional[str],
        ssh_head_proxy: Optional[SSHConnectionParams],
        ssh_head_proxy_private_key: Optional[str],
    ):
        payload = {
            "job_id": job_submission.id.hex,
            "app_port": get_service_port(job_spec, configuration),
            "ssh_head_proxy": ssh_head_proxy.model_dump() if ssh_head_proxy is not None else None,
            "ssh_head_proxy_private_key": ssh_head_proxy_private_key,
        }
        jpd = job_submission.job_provisioning_data
        assert jpd is not None
        assert jpd.hostname is not None
        assert jpd.ssh_port is not None
        payload["internal_ip"] = jpd.internal_ip
        if not jpd.dockerized:
            payload.update(
                {
                    "ssh_port": jpd.ssh_port,
                    "ssh_host": f"{jpd.username}@{jpd.hostname}",
                    "ssh_proxy": jpd.ssh_proxy.model_dump() if jpd.ssh_proxy is not None else None,
                }
            )
        else:
            ssh_port = DSTACK_RUNNER_SSH_PORT
            jrd = job_submission.job_runtime_data
            if jrd is not None and jrd.ports is not None:
                ssh_port = jrd.ports.get(ssh_port, ssh_port)
            payload.update(
                {
                    "ssh_port": ssh_port,
                    "ssh_host": "root@localhost",
                    "ssh_proxy": SSHConnectionParams(
                        hostname=jpd.hostname,
                        username=jpd.username,
                        port=jpd.ssh_port,
                    ).model_dump(),
                    "ssh_proxy_private_key": instance_project_ssh_private_key,
                }
            )
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/services/{run_name}/replicas/register"),
            json=payload,
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def update_replica_proxy_jump_keys(
        self, updates: list[ReplicaProxyJumpKeyUpdate]
    ) -> dict[str, str]:
        """Send one synchronization batch of SSH fleet `proxy_jump` key replacements.

        The gateway preserves existing service tunnels and saves successful updates
        once. Return failures by job ID; the next sync retries keys still different.
        """
        resp = await self._client.post(
            self._url("/api/registry/replicas/proxy_jump_keys"),
            json={"replicas": [item.model_dump() for item in updates]},
        )
        resp.raise_for_status()
        self.is_server_ready = True
        return UpdateReplicaProxyJumpKeysResponse.model_validate(resp.json()).failures

    async def unregister_replica(self, project: str, run_name: str, job_id: uuid.UUID):
        resp = await self._client.post(
            self._url(
                f"/api/registry/{project}/services/{run_name}/replicas/{job_id.hex}/unregister"
            )
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def set_service_id(self, project: str, run_name: str, run_id: uuid.UUID) -> None:
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/services/{run_name}/set_id"),
            json={"id": run_id.hex},
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def register_openai_entrypoint(
        self, project: str, domain: str, https: bool, read_timeout: int
    ):
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/entrypoints/register"),
            json={
                "domain": domain,
                "https": https,
                "read_timeout": read_timeout,
            },
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def register_import(
        self, importer_project: str, export_id: uuid.UUID, exporter_project: str, name: str
    ) -> None:
        resp = await self._client.post(
            self._url(f"/api/registry/{importer_project}/imports/register"),
            json=RegisterImportRequest(
                export_id=export_id.hex,
                exporter_project=exporter_project,
                name=name,
            ).model_dump(),
        )
        resp.raise_for_status()
        self.is_server_ready = True

    async def unregister_import(
        self, importer_project: str, export_id: uuid.UUID, name: str
    ) -> None:
        resp = await self._client.post(
            self._url(f"/api/registry/{importer_project}/imports/unregister"),
            json=UnregisterImportRequest(export_id=export_id.hex, name=name).model_dump(),
        )
        resp.raise_for_status()
        self.is_server_ready = True

    async def list_imports(self) -> list[ImportListItem]:
        resp = await self._client.get(self._url("/api/registry/imports/list"))
        resp.raise_for_status()
        self.is_server_ready = True
        return validate_json_extra_ignore(ImportListResponse, resp.content).imports

    async def list_services(self) -> list[ServiceListItem]:
        """Deprecated in favor of `get_state_summary`."""
        # TODO: drop when most users upgrade to 0.22.9+
        resp = await self._client.get(self._url("/api/services/list"))
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        resp_parsed = validate_json_extra_ignore(ServiceListResponse, resp.content)
        self.is_server_ready = True
        return resp_parsed.services

    async def get_state_summary(self) -> Optional[StateSummaryResponse]:
        resp = await self._client.get(self._url("/api/state/get_summary"))
        if resp.status_code == 404:
            # An older gateway not yet updated to 0.22.9+
            # TODO: drop when most users upgrade to 0.22.9+
            return None
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        resp_parsed = validate_json_extra_ignore(StateSummaryResponse, resp.content)
        self.is_server_ready = True
        return resp_parsed

    async def submit_gateway_config(self, config: ConfigRequest) -> None:
        resp = await self._client.post(
            self._url("/api/config"), json=config.model_dump(mode="json")
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def info(self) -> dict:
        resp = await self._client.get(self._url("/"))
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True
        return resp.json()

    async def collect_stats(self) -> list[ServiceStats]:
        resp = await self._client.get(self._url("/api/stats/collect"))
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True
        resp_data = resp.json()
        if isinstance(resp_data, dict):
            # Avoid errors if gateway is updated to new format and current server replica isn't.
            # TODO: remove after a few releases
            return []
        return TypeAdapter(list[ServiceStats]).validate_python(resp_data)

    async def collect_metering(
        self, after: int, limit: int, timeout: float
    ) -> list[MeteringBatch]:
        """
        Returns up to `limit` metering batches with numbers above `after`, oldest first.
        The gateway deletes the batches up to `after`, so pass the number of the last saved batch.
        """
        resp = await self._client.post(
            self._url("/api/metering/collect"),
            json=CollectMeteringRequest(after=after, limit=limit).model_dump(),
            timeout=timeout,
        )
        resp.raise_for_status()
        self.is_server_ready = True
        return validate_json_extra_ignore(CollectMeteringResponse, resp.content).batches

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def get_gateway_endpoint_domain(service_domain: str) -> str:
    """Returns the domain where the gateway serves the models of the service."""
    return f"gateway.{service_domain.split('.', maxsplit=1)[1]}"


def gateway_error(data: dict) -> GatewayError:
    return GatewayError(msg=data["detail"])


class AsyncClientWrapper(httpx.AsyncClient):
    def __del__(self):
        try:
            asyncio.get_running_loop().create_task(self.aclose())
        except Exception:
            pass
