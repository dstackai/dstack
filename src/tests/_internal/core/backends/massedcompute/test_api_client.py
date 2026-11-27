import traceback

import pytest
import requests

from dstack._internal.core.backends.massedcompute.api_client import (
    API_URL,
    MassedComputeAPIClient,
    MassedComputeLaunchUnconfirmed,
)
from dstack._internal.core.errors import (
    BackendAuthError,
    ComputeError,
    VolumeDeletionPending,
    VolumeProvisioningError,
)


class TestLaunch:
    @pytest.mark.parametrize("visible", [True, False])
    def test_lost_response(self, requests_mock, visible):
        name = "dstack-main-gpu-abcdefgh12345678"
        vm_id = "465e97cc-77cc-47dd-bb7c-1835ee127f9f"
        other = {"name": "other", "uuid": "other-id", "status": "Running"}
        instances = [other]
        if visible:
            instances.append({"name": name, "uuid": vm_id.upper(), "status": "Initializing"})
        launch = requests_mock.post(f"{API_URL}/instance/launch", exc=requests.ReadTimeout)
        requests_mock.get(f"{API_URL}/instance", json={"runningInstances": instances})
        client = MassedComputeAPIClient("test-key")

        if visible:
            assert client.launch(name, "gpu_1x_pro_6000_blackwell", "true") == vm_id
        else:
            with pytest.raises(ComputeError, match="ReadTimeout"):
                client.launch(name, "gpu_1x_pro_6000_blackwell", "true")
        assert launch.call_count == 1

    @pytest.mark.parametrize(
        ("response", "unconfirmed"),
        [
            *[({"status_code": code}, False) for code in (401, 403, 404, 409, 422)],
            ({"exc": requests.ConnectTimeout}, False),
            *[({"status_code": code}, True) for code in (400, 408, 502)],
            ({"json": {"response": "invalid"}}, True),
        ],
    )
    def test_distinguishes_rejected_and_unconfirmed_volume_launches(
        self, requests_mock, response, unconfirmed
    ):
        requests_mock.post(f"{API_URL}/instance/launch", **response)
        with pytest.raises((BackendAuthError, ComputeError)) as exc:
            MassedComputeAPIClient("test").launch("vm", "gpu", "true", ["volume"])
        assert isinstance(exc.value, MassedComputeLaunchUnconfirmed) == unconfirmed


class TestCreateVolume:
    @pytest.mark.parametrize(
        "response",
        [{"status_code": code} for code in (401, 403, 404, 422)]
        + [{"exc": requests.ConnectTimeout}],
    )
    def test_reports_definite_rejection_without_volume_id(self, requests_mock, response):
        requests_mock.post(f"{API_URL}/storage-volumes", **response)
        with pytest.raises(VolumeProvisioningError) as rejected:
            MassedComputeAPIClient("test").create_volume("checkpoints")
        assert rejected.value.volume_id is None


class TestDeleteVolume:
    def test_retries_until_provider_confirms_deletion(self, requests_mock):
        volume_id = "78ee0ea9-4c18-4aa4-b0df-aa1212734d45"
        requests_mock.delete(
            f"{API_URL}/storage-volumes/{volume_id}",
            [
                {"status_code": 409},
                {"status_code": 202, "json": {"result": {"deleted": False}}},
                {"status_code": 200, "json": {"result": {"id": volume_id, "deleted": True}}},
                {"status_code": 404},
            ],
        )
        client = MassedComputeAPIClient("test")
        for _ in range(2):
            with pytest.raises(VolumeDeletionPending):
                client.delete_volume(volume_id)
        client.delete_volume(volume_id)
        client.delete_volume(volume_id)


class TestGetInstance:
    def test_invalid_response_keeps_password_out_of_traceback(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/instance/vm-id",
            json={"runningInstances": [{"uuid": "vm-id", "password": "vm-login-secret"}]},
        )
        with pytest.raises(ComputeError, match="Unexpected response") as result:
            MassedComputeAPIClient("test-key").get_instance("vm-id")

        assert "vm-login-secret" not in "".join(traceback.format_exception(result.value))
