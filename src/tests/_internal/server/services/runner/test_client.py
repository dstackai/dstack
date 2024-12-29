from collections.abc import Generator
from typing import Optional

import pytest
import requests_mock

from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.resources import Memory
from dstack._internal.core.models.volumes import InstanceMountPoint, VolumeMountPoint
from dstack._internal.server.schemas.runner import (
    HealthcheckResponse,
    JobResult,
    LegacyPullResponse,
)
from dstack._internal.server.services.runner.client import ShimClient, _parse_version
from dstack._internal.server.testing.common import get_volume, get_volume_configuration


class BaseShimClientTest:
    @pytest.fixture
    def adapter(self) -> Generator[requests_mock.Adapter, None, None]:
        adapter = requests_mock.Adapter()
        with requests_mock.Mocker(adapter=adapter):
            yield adapter
        return

    @pytest.fixture
    def client(self, request: pytest.FixtureRequest, adapter: requests_mock.Adapter) -> ShimClient:
        shim_version_marker = request.node.get_closest_marker("shim_version")
        if shim_version_marker is not None:
            healthcheck_resp = {"service": "dstack-shim", "version": shim_version_marker.args[0]}
            adapter.register_uri("GET", "/api/healthcheck", json=healthcheck_resp)
        return ShimClient(port=10998, hostname="localhost")

    def assert_request(
        self,
        adapter: requests_mock.Adapter,
        index: int,
        method: str,
        path: str,
        json: Optional[dict] = None,
    ):
        history = adapter.request_history
        assert index < len(history), "index out of history bounds"
        req = history[index]
        assert req.method == method
        assert req.path == path
        if json is not None:
            assert req.json() == json


class TestShimClientNegotiate(BaseShimClientTest):
    @pytest.mark.parametrize(
        ["expected_shim_version", "expected_api_version"],
        [
            # final versions with optional build metadata ("local segment" according to PEP 440);
            # boundary-value cases
            pytest.param((0, 18, 33), 1, marks=pytest.mark.shim_version("0.18.33")),
            pytest.param((0, 18, 33), 1, marks=pytest.mark.shim_version("0.18.33+build.1")),
            pytest.param((0, 18, 34), 2, marks=pytest.mark.shim_version("0.18.34")),
            pytest.param((0, 18, 34), 2, marks=pytest.mark.shim_version("0.18.34+build.1")),
            # looks like major-only version, but not a version at all (stgn build),
            # assuming the latest version
            pytest.param(None, 2, marks=pytest.mark.shim_version("1494")),
            # invalid versions, assuming local builds with the latest version
            pytest.param(None, 2, marks=pytest.mark.shim_version("latest")),
            pytest.param(None, 2, marks=pytest.mark.shim_version("0.17.0-next")),
            # even though this version is less than _FUTURE_API_MIN_VERSION, for the sake of
            # simplicity we assume that any non-final version is the latest; normally, users
            # should not use non-latest RC versions
            pytest.param(None, 2, marks=pytest.mark.shim_version("0.17.0rc1")),
        ],
    )
    def test(
        self,
        client: ShimClient,
        adapter: requests_mock.Adapter,
        expected_shim_version: Optional[tuple[int, int, int]],
        expected_api_version: int,
    ):
        assert not hasattr(client, "_shim_version")
        assert not hasattr(client, "_api_version")

        client._negotiate()

        assert client._shim_version == expected_shim_version
        assert client._api_version == expected_api_version
        assert adapter.call_count == 1
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")


@pytest.mark.shim_version("0.18.30")
class TestShimClientV1(BaseShimClientTest):
    def test_healthcheck(self, client: ShimClient, adapter: requests_mock.Adapter):
        resp = client.healthcheck()

        assert resp == HealthcheckResponse(service="dstack-shim", version="0.18.30")
        assert adapter.call_count == 1
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")

    def test_submit(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri("POST", "/api/submit", json={"state": "pulling"})
        volume = get_volume(
            name="vol",
            volume_id="vol-id",
            configuration=get_volume_configuration(backend=BackendType.GCP),
            external=False,
            device_name="/dev/sdv",
        )

        submitted = client.submit(
            username="",
            password="",
            image_name="debian",
            privileged=False,
            container_name="test-0-0",
            container_user="root",
            shm_size=None,
            public_keys=["project_key", "user_key"],
            ssh_user="dstack",
            ssh_key="host_key",
            mounts=[VolumeMountPoint(name="vol", path="/vol")],
            volumes=[volume],
            instance_mounts=[InstanceMountPoint(instance_path="/mnt/nfs/home", path="/home")],
        )

        assert submitted is True
        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        expected_request = {
            "username": "",
            "password": "",
            "image_name": "debian",
            "privileged": False,
            "container_name": "test-0-0",
            "container_user": "root",
            "shm_size": 0,
            "public_keys": ["project_key", "user_key"],
            "ssh_user": "dstack",
            "ssh_key": "host_key",
            "mounts": [{"name": "vol", "path": "/vol"}],
            "volumes": [
                {
                    "backend": "gcp",
                    "name": "vol",
                    "volume_id": "vol-id",
                    "init_fs": True,
                    "device_name": "/dev/sdv",
                }
            ],
            "instance_mounts": [{"instance_path": "/mnt/nfs/home", "path": "/home"}],
        }
        self.assert_request(adapter, 1, "POST", "/api/submit", expected_request)

    def test_submit_conflict(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri("POST", "/api/submit", status_code=409)

        submitted = client.submit(
            username="",
            password="",
            image_name="debian",
            privileged=False,
            container_name="test-0-0",
            container_user="root",
            shm_size=None,
            public_keys=["project_key", "user_key"],
            ssh_user="dstack",
            ssh_key="host_key",
            mounts=[],
            volumes=[],
            instance_mounts=[],
        )

        assert submitted is False
        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "POST", "/api/submit")

    def test_stop(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri("POST", "/api/stop", json={"state": "pending"})

        client.stop()

        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "POST", "/api/stop", {"force": False})

    def test_stop_force(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri("POST", "/api/stop", json={"state": "pending"})

        client.stop(force=True)

        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "POST", "/api/stop", {"force": True})

    def test_pull(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri(
            "GET",
            "/api/pull",
            json={
                "state": "pending",
                "result": {"reason": "CONTAINER_EXITED_WITH_ERROR", "reason_message": "killed"},
            },
        )

        resp = client.pull()

        assert resp == LegacyPullResponse(
            state="pending",
            result=JobResult(reason="CONTAINER_EXITED_WITH_ERROR", reason_message="killed"),
        )
        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "GET", "/api/pull")


@pytest.mark.shim_version("0.18.40")
class TestShimClientV2Compat(BaseShimClientTest):
    def test_healthcheck(self, client: ShimClient, adapter: requests_mock.Adapter):
        resp = client.healthcheck()

        assert resp == HealthcheckResponse(service="dstack-shim", version="0.18.40")
        assert adapter.call_count == 1
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")

    def test_submit(self, client: ShimClient, adapter: requests_mock.Adapter):
        tasks_url = "/api/tasks"
        legacy_task_url = f"{tasks_url}/00000000-0000-0000-0000-000000000000"
        remove_legacy_task_url = f"{legacy_task_url}/remove"
        adapter.register_uri(
            "GET",
            legacy_task_url,
            json={
                "id": "00000000-0000-0000-0000-000000000000",
                "status": "terminated",
                "termination_reason": "CONTAINER_EXITED_WITH_ERROR",
                "termination_message": "killed",
                "container_name": "horrible-mule-1-0-0-44f7cb95",  # ignored
            },
        )
        adapter.register_uri("POST", remove_legacy_task_url)
        adapter.register_uri("POST", tasks_url)
        volume = get_volume(
            name="vol",
            volume_id="vol-id",
            configuration=get_volume_configuration(backend=BackendType.GCP),
            external=False,
            device_name="/dev/sdv",
        )

        submitted = client.submit(
            username="user",
            password="pass",
            image_name="debian",
            privileged=True,
            container_name="test-0-0",
            container_user="root",
            shm_size=Memory.parse("512MB"),
            public_keys=["project_key", "user_key"],
            ssh_user="dstack",
            ssh_key="host_key",
            mounts=[VolumeMountPoint(name="vol", path="/vol")],
            volumes=[volume],
            instance_mounts=[InstanceMountPoint(instance_path="/mnt/nfs/home", path="/home")],
        )

        assert submitted is True
        assert adapter.call_count == 4
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "GET", legacy_task_url)
        self.assert_request(adapter, 2, "POST", remove_legacy_task_url)
        expected_request = {
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "test-0-0",
            "registry_username": "user",
            "registry_password": "pass",
            "image_name": "debian",
            "container_user": "root",
            "privileged": True,
            "gpu": -1,
            "cpu": 0,
            "memory": 0,
            "shm_size": 536870912,
            "volumes": [
                {
                    "backend": "gcp",
                    "name": "vol",
                    "volume_id": "vol-id",
                    "init_fs": True,
                    "device_name": "/dev/sdv",
                }
            ],
            "volume_mounts": [{"name": "vol", "path": "/vol"}],
            "instance_mounts": [{"instance_path": "/mnt/nfs/home", "path": "/home"}],
            "host_ssh_user": "dstack",
            "host_ssh_keys": ["host_key"],
            "container_ssh_keys": ["project_key", "user_key"],
        }
        self.assert_request(adapter, 3, "POST", tasks_url, expected_request)

    def test_submit_no_task(self, client: ShimClient, adapter: requests_mock.Adapter):
        tasks_url = "/api/tasks"
        legacy_task_url = f"{tasks_url}/00000000-0000-0000-0000-000000000000"
        adapter.register_uri("GET", legacy_task_url, status_code=404)
        adapter.register_uri("POST", tasks_url)
        volume = get_volume(
            name="vol",
            volume_id="vol-id",
            configuration=get_volume_configuration(backend=BackendType.GCP),
            external=False,
            device_name="/dev/sdv",
        )

        submitted = client.submit(
            username="user",
            password="pass",
            image_name="debian",
            privileged=True,
            container_name="test-0-0",
            container_user="root",
            shm_size=Memory.parse("512MB"),
            public_keys=["project_key", "user_key"],
            ssh_user="dstack",
            ssh_key="host_key",
            mounts=[VolumeMountPoint(name="vol", path="/vol")],
            volumes=[volume],
            instance_mounts=[InstanceMountPoint(instance_path="/mnt/nfs/home", path="/home")],
        )

        assert submitted is True
        assert adapter.call_count == 3
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "GET", legacy_task_url)
        expected_request = {
            "id": "00000000-0000-0000-0000-000000000000",
            "name": "test-0-0",
            "registry_username": "user",
            "registry_password": "pass",
            "image_name": "debian",
            "container_user": "root",
            "privileged": True,
            "gpu": -1,
            "cpu": 0,
            "memory": 0,
            "shm_size": 536870912,
            "volumes": [
                {
                    "backend": "gcp",
                    "name": "vol",
                    "volume_id": "vol-id",
                    "init_fs": True,
                    "device_name": "/dev/sdv",
                }
            ],
            "volume_mounts": [{"name": "vol", "path": "/vol"}],
            "instance_mounts": [{"instance_path": "/mnt/nfs/home", "path": "/home"}],
            "host_ssh_user": "dstack",
            "host_ssh_keys": ["host_key"],
            "container_ssh_keys": ["project_key", "user_key"],
        }
        self.assert_request(adapter, 2, "POST", tasks_url, expected_request)

    def test_submit_conflict(self, client: ShimClient, adapter: requests_mock.Adapter):
        tasks_url = "/api/tasks"
        legacy_task_url = f"{tasks_url}/00000000-0000-0000-0000-000000000000"
        adapter.register_uri(
            "GET",
            legacy_task_url,
            json={
                "id": "00000000-0000-0000-0000-000000000000",
                "status": "running",
                "termination_reason": "",
                "termination_message": "",
            },
        )
        adapter.register_uri("POST", tasks_url)
        volume = get_volume(
            name="vol",
            volume_id="vol-id",
            configuration=get_volume_configuration(backend=BackendType.GCP),
            external=False,
            device_name="/dev/sdv",
        )

        submitted = client.submit(
            username="user",
            password="pass",
            image_name="debian",
            privileged=True,
            container_name="test-0-0",
            container_user="root",
            shm_size=Memory.parse("512MB"),
            public_keys=["project_key", "user_key"],
            ssh_user="dstack",
            ssh_key="host_key",
            mounts=[VolumeMountPoint(name="vol", path="/vol")],
            volumes=[volume],
            instance_mounts=[InstanceMountPoint(instance_path="/mnt/nfs/home", path="/home")],
        )

        assert submitted is False
        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "GET", legacy_task_url)

    def test_stop(self, client: ShimClient, adapter: requests_mock.Adapter):
        url = "/api/tasks/00000000-0000-0000-0000-000000000000/terminate"
        adapter.register_uri(
            "POST",
            url,
            json={
                "id": "00000000-0000-0000-0000-000000000000",
                "status": "terminated",
                "termination_reason": "",
                "termination_message": "",
            },
        )

        client.stop()

        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        expected_request = {"termination_reason": "", "termination_message": "", "timeout": 10}
        self.assert_request(adapter, 1, "POST", url, expected_request)

    def test_stop_no_task(self, client: ShimClient, adapter: requests_mock.Adapter):
        url = "/api/tasks/00000000-0000-0000-0000-000000000000/terminate"
        adapter.register_uri("POST", url, status_code=404)

        client.stop()

        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        expected_request = {"termination_reason": "", "termination_message": "", "timeout": 10}
        self.assert_request(adapter, 1, "POST", url, expected_request)

    def test_stop_force(self, client: ShimClient, adapter: requests_mock.Adapter):
        url = "/api/tasks/00000000-0000-0000-0000-000000000000/terminate"
        adapter.register_uri(
            "POST",
            url,
            json={
                "id": "00000000-0000-0000-0000-000000000000",
                "status": "terminated",
                "termination_reason": "",
                "termination_message": "",
            },
        )

        client.stop(force=True)

        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        expected_request = {"termination_reason": "", "termination_message": "", "timeout": 0}
        self.assert_request(adapter, 1, "POST", url, expected_request)

    def test_pull(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri(
            "GET",
            "/api/tasks/00000000-0000-0000-0000-000000000000",
            json={
                "id": "00000000-0000-0000-0000-000000000000",
                "status": "terminated",
                "termination_reason": "CONTAINER_EXITED_WITH_ERROR",
                "termination_message": "killed",
                "container_name": "horrible-mule-1-0-0-44f7cb95",  # ignored
            },
        )

        resp = client.pull()

        assert resp == LegacyPullResponse(
            state="pending",
            result=JobResult(reason="CONTAINER_EXITED_WITH_ERROR", reason_message="killed"),
        )
        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "GET", "/api/tasks/00000000-0000-0000-0000-000000000000")

    def test_pull_no_task(self, client: ShimClient, adapter: requests_mock.Adapter):
        adapter.register_uri(
            "GET",
            "/api/tasks/00000000-0000-0000-0000-000000000000",
            status_code=404,
        )

        resp = client.pull()

        assert resp == LegacyPullResponse(
            state="pending",
            result=JobResult(reason="", reason_message=""),
        )
        assert adapter.call_count == 2
        self.assert_request(adapter, 0, "GET", "/api/healthcheck")
        self.assert_request(adapter, 1, "GET", "/api/tasks/00000000-0000-0000-0000-000000000000")


class TestParseVersion:
    @pytest.mark.parametrize(
        ["value", "expected"],
        [
            ["1.12", (1, 12, 0)],
            ["1.12.3", (1, 12, 3)],
            ["1.12.3.1", (1, 12, 3)],
            ["1.12.3+build.1", (1, 12, 3)],  # local builds are OK
        ],
    )
    def test_valid_final(self, value: str, expected: tuple[int, int, int]):
        assert _parse_version(value) == expected

    @pytest.mark.parametrize("value", ["1.12alpha1", "1.12.3rc1", "1.12.3.dev0"])
    def test_valid_pre_dev_local(self, value: str):
        assert _parse_version(value) is None

    @pytest.mark.parametrize("value", ["1", "1234"])
    def test_valid_major_only(self, value: str):
        assert _parse_version(value) is None

    @pytest.mark.parametrize("value", ["", "foo", "1.12.3-next.20241231"])
    def test_invalid(self, value: str):
        assert _parse_version(value) is None
