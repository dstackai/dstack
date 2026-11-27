import traceback

import pytest
import requests

from dstack._internal.core.backends.massedcompute.api_client import API_URL, MassedComputeAPIClient
from dstack._internal.core.errors import ComputeError


class TestLaunch:
    @pytest.mark.parametrize("visible", [True, False])
    def test_lost_response(self, requests_mock, visible):
        name = "dstack-main-gpu-abcdefgh12345678"
        vm_id = "465e97cc-77cc-47dd-bb7c-1835ee127f9f"
        other = {"name": "other", "uuid": "other-id", "status": "Running"}
        instances = [other]
        if visible:
            instances.append({"name": name, "uuid": vm_id, "status": "Initializing"})
        launch = requests_mock.post(f"{API_URL}/instance/launch", exc=requests.ReadTimeout)
        requests_mock.get(f"{API_URL}/instance", json={"runningInstances": instances})
        client = MassedComputeAPIClient("test-key")

        if visible:
            assert client.launch(name, "gpu_1x_pro_6000_blackwell", "true") == vm_id
        else:
            with pytest.raises(ComputeError, match="ReadTimeout"):
                client.launch(name, "gpu_1x_pro_6000_blackwell", "true")
        assert launch.call_count == 1


class TestGetInstance:
    def test_invalid_response_keeps_password_out_of_traceback(self, requests_mock):
        requests_mock.get(
            f"{API_URL}/instance/vm-id",
            json={"runningInstances": [{"uuid": "vm-id", "password": "vm-login-secret"}]},
        )
        with pytest.raises(ComputeError, match="Unexpected response") as result:
            MassedComputeAPIClient("test-key").get_instance("vm-id")

        assert "vm-login-secret" not in "".join(traceback.format_exception(result.value))
