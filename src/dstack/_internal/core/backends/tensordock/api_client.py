import uuid

import requests
import yaml

from dstack._internal.core.models.instances import InstanceType
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


class TensorDockAPIClient:
    def __init__(self, api_key: str, api_token: str):
        self.api_url = "https://marketplace.tensordock.com/api/v0".rstrip("/")
        self.api_key = api_key
        self.api_token = api_token
        self.s = requests.Session()

    def auth_test(self) -> bool:
        resp = self.s.post(
            self._url("/auth/test"), data={"api_key": self.api_key, "api_token": self.api_token}
        )
        resp.raise_for_status()
        return resp.json()["success"]

    def get_hostnode(self, hostnode_id: str) -> dict:
        logger.debug("Fetching hostnode %s", hostnode_id)
        resp = self.s.get(self._url(f"/client/deploy/hostnodes/{hostnode_id}"))
        resp.raise_for_status()
        data = resp.json()
        if not data["success"]:
            raise requests.HTTPError(data)
        return data["hostnode"]

    def deploy_single(self, instance_name: str, instance: InstanceType, cloudinit: dict) -> dict:
        hostnode = self.get_hostnode(instance.name)
        gpu = instance.resources.gpus[0]
        for gpu_model in hostnode["specs"]["gpu"].keys():
            if gpu_model.endswith(f"-{gpu.memory_mib // 1024}gb"):
                if gpu.name.lower() in gpu_model.lower():
                    break
        else:
            raise ValueError(f"Can't find GPU on the hostnode: {gpu.name}")
        form = {
            "api_key": self.api_key,
            "api_token": self.api_token,
            "password": uuid.uuid4().hex,  # we disable the password auth, but it's required
            "name": instance_name,
            "gpu_count": len(instance.resources.gpus),
            "gpu_model": gpu_model,
            "vcpus": instance.resources.cpus,
            "ram": instance.resources.memory_mib // 1024,
            "external_ports": "{%s}" % hostnode["networking"]["ports"][0],
            "internal_ports": "{22}",
            "hostnode": instance.name,
            "storage": 100,  # TODO(egor-s): take from instance.resources
            "operating_system": "Ubuntu 22.04 LTS",
            "cloudinit_script": yaml.dump(cloudinit).replace("\n", "\\n"),
        }
        logger.debug(
            "Deploying instance hostnode=%s, cpus=%s, memory=%s, gpu=%sx %s",
            form["hostnode"],
            form["vcpus"],
            form["ram"],
            form["gpu_count"],
            form["gpu_model"],
        )
        resp = self.s.post(self._url("/client/deploy/single"), data=form)
        resp.raise_for_status()
        data = resp.json()
        if not data["success"]:
            raise requests.HTTPError(data)
        data["password"] = form["password"]
        return data

    def delete_single(self, instance_id: str):
        logger.debug("Deleting instance %s", instance_id)
        resp = self.s.post(
            self._url("/client/delete/single"),
            data={
                "api_key": self.api_key,
                "api_token": self.api_token,
                "server": instance_id,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if not data["success"]:
            raise requests.HTTPError(data)

    def _url(self, path):
        return f"{self.api_url}/{path.lstrip('/')}"
