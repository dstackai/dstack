from typing import Optional
from urllib.parse import urlparse

import httpx

from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.runs import JobProvisioningData, Run

GATEWAY_MANAGEMENT_PORT = 8000


class GatewayClient:
    def __init__(self, uds: Optional[str] = None, port: Optional[int] = None):
        if uds is None and port is None:
            raise ValueError("Either uds or port should be specified")
        if uds is not None and port is not None:
            raise ValueError("Either uds or port should be specified, not both")

        self.base_url = "http://gateway" if uds else f"http://localhost:{port}"
        self.s = httpx.Client(transport=httpx.HTTPTransport(uds=uds) if uds else None, timeout=30)

    def register_service(self, run: Run, job_provisioning_data: JobProvisioningData):
        conf = run.run_spec.configuration
        payload = {
            "public_domain": urlparse(run.service.url).hostname,
            "app_port": conf.port.container_port,
            "auth": conf.auth,
            "options": run.service.options,
        }
        ssh_proxy = job_provisioning_data.ssh_proxy
        if ssh_proxy is None:
            payload[
                "ssh_host"
            ] = f"{job_provisioning_data.username}@{job_provisioning_data.hostname}"
            payload["ssh_port"] = job_provisioning_data.ssh_port
            if job_provisioning_data.dockerized:
                payload["docker_ssh_host"] = "root@localhost"
                payload["docker_ssh_port"] = 10022
        else:
            payload["ssh_host"] = f"{ssh_proxy.username}@{ssh_proxy.hostname}"
            payload["ssh_port"] = ssh_proxy.port
            payload[
                "docker_ssh_host"
            ] = f"{job_provisioning_data.username}@{job_provisioning_data.hostname}"
            payload["docker_ssh_port"] = job_provisioning_data.ssh_port
        resp = self.s.post(self._url(f"/api/registry/{run.project_name}/register"), json=payload)
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()

    def register_openai_entrypoint(self, project: str, domain: str):
        resp = self.s.post(
            self._url(f"/api/registry/{project}/openai/register"), json={"domain": domain}
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()

    def unregister_service(self, project: str, public_domain: str):
        resp = self.s.post(
            self._url(f"/api/registry/{project}/unregister"), json={"public_domain": public_domain}
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()

    def preflight(self, project: str, domain: str, private_ssh_key: str, options: dict):
        if "openai" in options:
            # TODO(egor-s): custom entrypoint domain
            entrypoint = f"gateway.{domain.split('.', maxsplit=1)[1]}"
            self.register_openai_entrypoint(project, entrypoint)
        resp = self.s.post(
            self._url(f"/api/registry/{project}/preflight"),
            json={"public_domain": domain, "ssh_private_key": private_ssh_key, "options": options},
        )
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()

    def info(self) -> dict:
        resp = self.s.get(self._url("/"))
        if resp.status_code == 400:
            raise gateway_error(resp.json())
        resp.raise_for_status()
        return resp.json()

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def gateway_error(data: dict) -> GatewayError:
    detail = data["detail"]
    return GatewayError(msg=f"{detail['error']}: {detail['message']}")
