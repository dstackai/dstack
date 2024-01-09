import requests

from dstack._internal.core.errors import GatewayError
from dstack._internal.core.models.runs import Job, JobProvisioningData

GATEWAY_MANAGEMENT_PORT = 8000


class GatewayClient:
    def __init__(self, port: int = GATEWAY_MANAGEMENT_PORT):
        self.base_url = f"http://localhost:{port}"
        self.s = requests.Session()

    def register_service(self, project: str, job: Job, job_provisioning_data: JobProvisioningData):
        payload = {
            "public_domain": job.job_spec.gateway.hostname,
            "app_port": job.job_spec.gateway.service_port,
            "ssh_host": f"{job_provisioning_data.username}@{job_provisioning_data.hostname}",
            "ssh_port": job_provisioning_data.ssh_port,
            "options": job.job_spec.gateway.options,
        }
        if job_provisioning_data.dockerized:
            payload["docker_ssh_host"] = f"root@localhost"
            payload["docker_ssh_port"] = 10022
        resp = self.s.post(self._url(f"/api/registry/{project}/register"), json=payload)
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

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"


def gateway_error(data: dict) -> GatewayError:
    detail = data["detail"]
    return GatewayError(msg=f"{detail['error']}: {detail['message']}")
