import asyncio
import uuid
from typing import Dict, Optional

import httpx
from pydantic import BaseModel, parse_obj_as

from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.runs import JobSubmission, Run
from dstack._internal.server import settings

GATEWAY_MANAGEMENT_PORT = 8000


class Stat(BaseModel):
    requests: int
    request_time: float


StatsCollectResponse = Dict[str, Dict[int, Stat]]


class GatewayClient:
    def __init__(self, uds: Optional[str] = None, port: Optional[int] = None):
        if uds is None and port is None:
            raise ValueError("Either uds or port should be specified")
        if uds is not None and port is not None:
            raise ValueError("Either uds or port should be specified, not both")

        # Shows that the gateway's HTTP server has started. Should become True
        # in submit_gateway_config during gateway setup. If setup fails, it
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
        domain: str,
        service_https: bool,
        gateway_https: bool,
        auth: bool,
        options: dict,
        ssh_private_key: str,
    ):
        if "openai" in options:
            entrypoint = f"gateway.{domain.split('.', maxsplit=1)[1]}"
            await self.register_openai_entrypoint(project, entrypoint, gateway_https)

        payload = {
            "run_id": run_id.hex,
            "domain": domain,
            "https": service_https,
            "auth": auth,
            "options": options,
            "ssh_private_key": ssh_private_key,
        }
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/services/register"), json=payload
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def unregister_service(self, project: str, run_id: uuid.UUID):
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/services/{run_id.hex}/unregister")
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def register_replica(self, run: Run, job_submission: JobSubmission):
        payload = {
            "job_id": job_submission.id.hex,
            "app_port": run.run_spec.configuration.port.container_port,
        }
        jpd = job_submission.job_provisioning_data
        if not jpd.dockerized:
            payload.update(
                {
                    "ssh_port": jpd.ssh_port,
                    "ssh_host": f"{jpd.username}@{jpd.hostname}",
                }
            )
            if jpd.ssh_proxy is not None:
                payload.update(
                    {
                        "ssh_jump_port": jpd.ssh_proxy.port,
                        "ssh_jump_host": f"{jpd.ssh_proxy.username}@{jpd.ssh_proxy.hostname}",
                    }
                )
        else:
            payload.update(
                {
                    "ssh_port": 10022,
                    "ssh_host": "root@localhost",
                    "ssh_jump_port": jpd.ssh_port,
                    "ssh_jump_host": f"{jpd.username}@{jpd.hostname}",
                }
            )

        resp = await self._client.post(
            self._url(f"/api/registry/{run.project_name}/services/{run.id.hex}/replicas/register"),
            json=payload,
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def unregister_replica(self, project: str, run_id: uuid.UUID, job_id: uuid.UUID):
        resp = await self._client.post(
            self._url(
                f"/api/registry/{project}/services/{run_id.hex}/replicas/{job_id.hex}/unregister"
            )
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def register_openai_entrypoint(self, project: str, domain: str, https: bool):
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/entrypoints/register"),
            json={
                "module": "openai",
                "domain": domain,
                "https": https,
            },
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

    async def submit_gateway_config(self) -> None:
        resp = await self._client.post(
            self._url("/api/config"),
            json={
                "acme_server": settings.ACME_SERVER,
                "acme_eab_kid": settings.ACME_EAB_KID,
                "acme_eab_hmac_key": settings.ACME_EAB_HMAC_KEY,
            },
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

    async def collect_stats(self) -> StatsCollectResponse:
        resp = await self._client.get(self._url("/api/stats/collect"))
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True
        return parse_obj_as(StatsCollectResponse, resp.json())

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def gateway_error(data: dict) -> GatewayError:
    return GatewayError(msg=f"{data['error']}: {data['message']}")


class AsyncClientWrapper(httpx.AsyncClient):
    def __del__(self):
        try:
            asyncio.get_running_loop().create_task(self.aclose())
        except Exception:
            pass
