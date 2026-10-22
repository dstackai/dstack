import pytest

from dstack._internal.core.backends.runpod.api_client import (
    API_V2_URL,
    RunpodApiClient,
    RunpodV2ClientError,
)
from dstack._internal.core.errors import BackendInvalidCredentialsError


def _client() -> RunpodApiClient:
    return RunpodApiClient(api_key="test")


def _error(status: int, detail: str, errors: list[str] | None = None) -> dict:
    error = {"title": "Error", "status": status, "detail": detail}
    if errors is not None:
        error["errors"] = errors
    return error


class TestRunpodApiClientCreatePod:
    def test_gpu_pod(self, requests_mock):
        requests_mock.post(f"{API_V2_URL}/pods", status_code=201, json={"id": "pod-1"})

        pod = _client().create_pod(
            name="test-pod",
            cloud="SECURE",
            data_center_ids=["EU-RO-1"],
            gpu_type_id="NVIDIA H100 80GB HBM3",
            gpu_count=2,
            min_cpu_count_per_gpu=8,
            min_memory_in_gb_per_gpu=125,
            container_disk_in_gb=100,
            network_volume_id="vol-1",
            volume_mount_path="/data",
            image_name="dstackai/base:latest",
            container_registry_credentials_id="creds-1",
            entrypoint=["/bin/sh"],
            cmd=["-c", "echo hi"],
            ports=["10022/tcp"],
            env={"RUNPOD_POD_USER": "0"},
        )

        assert pod["id"] == "pod-1"
        assert requests_mock.last_request.headers["Authorization"] == "Bearer test"
        assert requests_mock.last_request.json() == {
            "name": "test-pod",
            "cloud": "SECURE",
            "dataCenterIds": ["EU-RO-1"],
            "gpu": {
                "id": "NVIDIA H100 80GB HBM3",
                "count": 2,
                "minCudaVersion": "12.8",
                "minVcpuCountPerGpu": 8,
                "minRamPerGpu": 125,
            },
            "disk": 100,
            "mounts": {"network": [{"volumeId": "vol-1", "path": "/data"}]},
            "image": "dstackai/base:latest",
            "registry": "creds-1",
            "entrypoint": ["/bin/sh"],
            "cmd": ["-c", "echo hi"],
            "ports": ["10022/tcp"],
            "env": {"RUNPOD_POD_USER": "0"},
        }

    def test_cpu_pod(self, requests_mock):
        requests_mock.post(f"{API_V2_URL}/pods", status_code=201, json={"id": "pod-1"})

        _client().create_pod(
            name="test-pod",
            cloud="SECURE",
            cpu_type_id="cpu3c",
            cpu_count=4,
            container_disk_in_gb=20,
            image_name="dstackai/base:latest",
            entrypoint=["/bin/sh"],
            cmd=["-c", "echo hi"],
        )

        assert requests_mock.last_request.json() == {
            "name": "test-pod",
            "cloud": "SECURE",
            "cpu": {"id": "cpu3c", "vcpuCount": 4},
            "disk": 20,
            "image": "dstackai/base:latest",
            "entrypoint": ["/bin/sh"],
            "cmd": ["-c", "echo hi"],
        }

    def test_rejects_both_gpu_and_cpu(self):
        with pytest.raises(ValueError, match="Exactly one"):
            _client().create_pod(
                name="test-pod",
                cloud="SECURE",
                gpu_type_id="NVIDIA H100 80GB HBM3",
                cpu_type_id="cpu3c",
                container_disk_in_gb=20,
                image_name="dstackai/base:latest",
                entrypoint=["/bin/sh"],
                cmd=["-c", "echo hi"],
            )


class TestRunpodApiClientErrors:
    def test_v2_error_response(self, requests_mock):
        requests_mock.post(
            f"{API_V2_URL}/registries",
            status_code=422,
            json=_error(422, "Request validation failed.", ["$: missing property 'name'"]),
        )

        with pytest.raises(RunpodV2ClientError) as exc_info:
            _client().create_container_registry_credentials(name="", username="u", password="p")

        assert exc_info.value.status == 422
        assert exc_info.value.detail == "Request validation failed."
        assert exc_info.value.errors == ["$: missing property 'name'"]
        assert str(exc_info.value) == (
            "422: Error: Request validation failed: [\"$: missing property 'name'\"]"
        )

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_auth_error_response(self, requests_mock, status_code: int):
        requests_mock.get(
            f"{API_V2_URL}/account/ssh-keys",
            status_code=status_code,
            json=_error(status_code, "Invalid token"),
        )

        assert _client().validate_api_key() is False

    def test_non_json_auth_error_response(self, requests_mock):
        requests_mock.get(
            f"{API_V2_URL}/pods/pod-1",
            status_code=403,
            reason="Forbidden",
            text="<html><body>Access denied</body></html>",
        )

        with pytest.raises(BackendInvalidCredentialsError, match="Forbidden: <html>"):
            _client().get_pod("pod-1")

    def test_non_json_error_response(self, requests_mock):
        requests_mock.get(
            f"{API_V2_URL}/pods/pod-1",
            status_code=429,
            reason="Too Many Requests",
            text="<html>\n<body>" + "x" * 1000 + "</body>\n</html>",
        )

        with pytest.raises(RunpodV2ClientError) as exc_info:
            _client().get_pod("pod-1")

        assert exc_info.value.status == 429
        assert exc_info.value.title == "Too Many Requests"
        assert exc_info.value.detail.startswith("<html> <body>xxx")
        assert len(exc_info.value.detail) == 200


class TestRunpodApiClientNotFound:
    def test_get_pod(self, requests_mock):
        requests_mock.get(f"{API_V2_URL}/pods/pod-1", status_code=404, json=_error(404, "-"))

        assert _client().get_pod("pod-1") is None

    def test_terminate_pod(self, requests_mock):
        requests_mock.delete(f"{API_V2_URL}/pods/pod-1", status_code=404, json=_error(404, "-"))

        assert _client().terminate_pod("pod-1") is False

    def test_delete_cluster(self, requests_mock):
        requests_mock.delete(
            f"{API_V2_URL}/clusters/cluster-1", status_code=404, json=_error(404, "-")
        )

        assert _client().delete_cluster("cluster-1") is False

    def test_delete_network_volume(self, requests_mock):
        requests_mock.delete(
            f"{API_V2_URL}/network-volumes/vol-1", status_code=404, json=_error(404, "-")
        )

        assert _client().delete_network_volume("vol-1") is False

    def test_other_errors_are_raised(self, requests_mock):
        requests_mock.delete(
            f"{API_V2_URL}/pods/pod-1",
            status_code=409,
            json=_error(409, "Pod belongs to a cluster"),
        )

        with pytest.raises(RunpodV2ClientError):
            _client().terminate_pod("pod-1")
