import asyncio
import uuid
from typing import Optional

import httpx
from pydantic import parse_obj_as

from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.configurations import RateLimit
from dstack._internal.core.models.instances import SSHConnectionParams
from dstack._internal.core.models.runs import JobSpec, JobSubmission, Run, get_service_port
from dstack._internal.proxy.gateway.schemas.stats import ServiceStats
from dstack._internal.server import settings


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
        run_name: str,
        domain: str,
        service_https: bool,
        gateway_https: bool,
        auth: bool,
        client_max_body_size: int,
        options: dict,
        rate_limits: list[RateLimit],
        ssh_private_key: str,
    ):
        if "openai" in options:
            entrypoint = f"gateway.{domain.split('.', maxsplit=1)[1]}"
            await self.register_openai_entrypoint(project, entrypoint, gateway_https)

        payload = {
            "run_name": run_name,
            "domain": domain,
            "https": service_https,
            "auth": auth,
            "client_max_body_size": client_max_body_size,
            "options": options,
            "rate_limits": [limit.dict() for limit in rate_limits],
            "ssh_private_key": ssh_private_key,
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
        run: Run,
        job_spec: JobSpec,
        job_submission: JobSubmission,
        ssh_head_proxy: Optional[SSHConnectionParams],
        ssh_head_proxy_private_key: Optional[str],
    ):
        assert run.run_spec.configuration.type == "service"
        payload = {
            "job_id": job_submission.id.hex,
            "app_port": get_service_port(job_spec, run.run_spec.configuration),
            "ssh_head_proxy": ssh_head_proxy.dict() if ssh_head_proxy is not None else None,
            "ssh_head_proxy_private_key": ssh_head_proxy_private_key,
        }
        jpd = job_submission.job_provisioning_data
        assert jpd is not None
        assert jpd.hostname is not None
        assert jpd.ssh_port is not None
        if not jpd.dockerized:
            payload.update(
                {
                    "ssh_port": jpd.ssh_port,
                    "ssh_host": f"{jpd.username}@{jpd.hostname}",
                    "ssh_proxy": jpd.ssh_proxy.dict() if jpd.ssh_proxy is not None else None,
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
                    ).dict(),
                }
            )
        resp = await self._client.post(
            self._url(
                f"/api/registry/{run.project_name}/services/{run.run_spec.run_name}/replicas/register"
            ),
            json=payload,
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        self.is_server_ready = True

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

    async def register_openai_entrypoint(self, project: str, domain: str, https: bool):
        resp = await self._client.post(
            self._url(f"/api/registry/{project}/entrypoints/register"),
            json={
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
        return parse_obj_as(list[ServiceStats], resp_data)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def gateway_error(data: dict) -> GatewayError:
    return GatewayError(msg=data["detail"])


class AsyncClientWrapper(httpx.AsyncClient):
    def __del__(self):
        try:
            asyncio.get_running_loop().create_task(self.aclose())
        except Exception:
            pass
