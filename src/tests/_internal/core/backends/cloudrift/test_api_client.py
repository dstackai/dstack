import pytest
import requests

from dstack._internal.core.backends.cloudrift.api_client import (
    CLOUDRIFT_SERVER_ADDRESS,
    RiftClient,
)
from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError

API_ROOT = f"{CLOUDRIFT_SERVER_ADDRESS}/api/v1"


def _response(data, version="2025-01-29"):
    return {"version": version, "data": data}


def _recipes():
    return {
        "groups": [
            {
                "name": "Linux",
                "tags": ["VM"],
                "recipes": [
                    {
                        "name": "Ubuntu 24.04 Server",
                        "tags": ["nvidia-driver"],
                        "details": {"VirtualMachine": {"image_url": "https://images/nvidia.img"}},
                    },
                    {
                        "name": "Ubuntu 24.04 Server (AMD)",
                        "tags": ["amd-driver"],
                        "details": {"VirtualMachine": {"image_url": "https://images/amd.img"}},
                    },
                ],
            }
        ]
    }


class TestRiftClient:
    @pytest.mark.parametrize(
        ("endpoint", "data"),
        [
            ("auth/me", {"email": "test@example.com"}),
            ("instance-types/list", {"instance_types": []}),
            ("recipes/list", {"groups": []}),
            ("instances/list", {"instances": []}),
            ("instances/rent", {"instance_ids": []}),
            ("instances/terminate", {"terminated": []}),
        ],
    )
    def test_uses_current_production_protocol(self, requests_mock, endpoint, data):
        # CloudRift rejects the old pin on provisioning endpoints, even though
        # auth and instance-type discovery still accept it.
        requests_mock.post(
            f"{API_ROOT}/{endpoint}",
            additional_matcher=lambda request: request.json()["version"] == "2026-10-12",
            json=_response(data),
        )

        assert RiftClient("test-key")._make_request(endpoint, {}) == data
        assert requests_mock.last_request.headers["X-API-Key"] == "test-key"

    @pytest.mark.parametrize("status_code", [401, 403])
    def test_rejects_invalid_credentials(self, requests_mock, status_code):
        requests_mock.post(f"{API_ROOT}/auth/me", status_code=status_code, text="invalid key")

        assert RiftClient("test-key").validate_api_key() is False
        with pytest.raises(BackendInvalidCredentialsError, match="invalid key"):
            RiftClient("test-key")._make_request("auth/me")

    def test_preserves_http_errors(self, requests_mock):
        requests_mock.post(f"{API_ROOT}/recipes/list", status_code=400, text="unsupported version")

        with pytest.raises(requests.HTTPError) as exc_info:
            RiftClient("test-key").list_recipes()

        assert exc_info.value.response is not None
        assert exc_info.value.response.text == "unsupported version"


class TestRiftClientDeployInstance:
    @pytest.mark.parametrize("gpu_vendor", ["nvidia", "amd"])
    def test_discovers_image_and_rents_vm(self, requests_mock, gpu_vendor):
        requests_mock.post(f"{API_ROOT}/recipes/list", json=_response(_recipes()))
        requests_mock.post(
            f"{API_ROOT}/instances/rent",
            json=_response({"instance_ids": ["instance-id"]}, version="2026-09-09"),
        )

        instance_ids = RiftClient("test-key").deploy_instance(
            instance_type="rtx59-7-24-800-ig.1",
            region="ap_northeast_kr_se_1",
            ssh_keys=["ssh-rsa test"],
            cmd="start-shim",
            gpu_vendor=gpu_vendor,
        )

        assert instance_ids == ["instance-id"]
        assert requests_mock.last_request.json() == {
            "version": "2026-10-12",
            "data": {
                "config": {
                    "VirtualMachine": {
                        "cloudinit_commands": "start-shim",
                        "image_url": f"https://images/{gpu_vendor}.img",
                        "ssh_key": {"PublicKeys": ["ssh-rsa test"]},
                    }
                },
                "selector": {
                    "ByInstanceTypeAndLocation": {
                        "datacenters": ["ap_northeast_kr_se_1"],
                        "instance_type": "rtx59-7-24-800-ig.1",
                    }
                },
                "with_public_ip": True,
            },
        }

    def test_does_not_rent_without_suitable_image(self, requests_mock):
        requests_mock.post(f"{API_ROOT}/recipes/list", json=_response({"groups": []}))

        with pytest.raises(BackendError, match="No suitable VM image"):
            RiftClient("test-key").deploy_instance("type.1", "region", [], "start-shim")

        assert requests_mock.call_count == 1


class TestRiftClientListInstances:
    def test_selects_active_statuses_and_requests_connection_info(self, requests_mock):
        instances = [{"id": "instance-id", "host_address": "192.0.2.1"}]
        requests_mock.post(
            f"{API_ROOT}/instances/list",
            json=_response({"instances": instances}, version="2026-08-05"),
        )

        assert RiftClient("test-key").list_instances() == instances
        assert requests_mock.last_request.json()["data"] == {
            "selector": {"ByStatus": {"statuses": ["Initializing", "Active", "Deactivating"]}},
            "mask": {"with_connection_info": True, "with_credentials": True},
        }

    @pytest.mark.parametrize("instance_ids", [[], ["instance-id", "other-id"]])
    def test_selects_requested_ids(self, requests_mock, instance_ids):
        requests_mock.post(f"{API_ROOT}/instances/list", json=_response({"instances": []}))

        assert RiftClient("test-key").list_instances(instance_ids) == []
        assert requests_mock.last_request.json()["data"]["selector"] == {"ById": instance_ids}

    @pytest.mark.parametrize("found", [True, False])
    def test_gets_instance_by_id_with_connection_info(self, requests_mock, found):
        instance = {
            "id": "instance-id",
            "node_mode": "VirtualMachine",
            "host_address": "192.0.2.1",
            "port_mappings": [[22, 57001]],
            "virtual_machines": [{"ready": True}],
        }
        requests_mock.post(
            f"{API_ROOT}/instances/list",
            json=_response({"instances": [instance] if found else []}, version="2026-08-05"),
        )

        assert RiftClient("test-key").get_instance_by_id("instance-id") == (
            instance if found else None
        )
        assert requests_mock.last_request.json()["data"] == {
            "selector": {"ById": ["instance-id"]},
            "mask": {"with_connection_info": True, "with_credentials": True},
        }


class TestRiftClientTerminateInstance:
    def test_terminates_requested_instance(self, requests_mock):
        requests_mock.post(
            f"{API_ROOT}/instances/terminate",
            json=_response({"terminated": [{"id": "instance-id"}]}, version="2026-08-05"),
        )

        assert RiftClient("test-key").terminate_instance("instance-id") is True
        assert requests_mock.last_request.json() == {
            "version": "2026-10-12",
            "data": {"selector": {"ById": ["instance-id"]}},
        }

    @pytest.mark.parametrize("status", [None, "Inactive", "Deactivating", "Active"])
    def test_checks_already_terminated_instance(self, requests_mock, status):
        requests_mock.post(f"{API_ROOT}/instances/terminate", json=_response({"terminated": []}))
        requests_mock.post(
            f"{API_ROOT}/instances/list",
            json=_response({"instances": [{"status": status}] if status else []}),
        )

        assert RiftClient("test-key").terminate_instance("instance-id") is (
            status in (None, "Inactive")
        )
