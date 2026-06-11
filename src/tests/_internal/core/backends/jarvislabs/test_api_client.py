import pytest
import requests
from gpuhunt.providers.jarvislabs import API_URL

from dstack._internal.core.backends.jarvislabs.api_client import (
    JarvisLabsAPIClient,
    is_cpu_vm,
)
from dstack._internal.core.errors import BackendError, BackendInvalidCredentialsError


def test_validate_api_key_returns_false_on_unauthorized(requests_mock):
    requests_mock.get(f"{API_URL}/users/user_info", status_code=401)

    assert JarvisLabsAPIClient("bad").validate_api_key() is False


def test_get_user_info_raises_invalid_credentials_on_forbidden(requests_mock):
    requests_mock.get(f"{API_URL}/users/user_info", status_code=403)

    with pytest.raises(BackendInvalidCredentialsError):
        JarvisLabsAPIClient("bad").get_user_info()


def test_make_request_wraps_request_errors(requests_mock):
    requests_mock.get(
        f"{API_URL}/users/user_info",
        exc=requests.ConnectTimeout("timed out"),
    )

    with pytest.raises(BackendError, match="JarvisLabs request failed"):
        JarvisLabsAPIClient("token").get_user_info()


def test_get_user_info_rejects_non_json_success_response(requests_mock):
    requests_mock.get(f"{API_URL}/users/user_info", text="ok")

    with pytest.raises(BackendError, match="Unexpected non-JSON JarvisLabs response"):
        JarvisLabsAPIClient("token").get_user_info()


def test_add_ssh_key_if_needed_reuses_existing_key(requests_mock):
    public_key = "ssh-rsa AAAA test-comment"
    requests_mock.get(
        f"{API_URL}/ssh/",
        json=[{"ssh_key": "ssh-rsa AAAA another-comment", "key_name": "existing"}],
    )

    JarvisLabsAPIClient("token").add_ssh_key_if_needed(public_key)

    assert requests_mock.call_count == 1


def test_add_ssh_key_if_needed_adds_missing_key(requests_mock):
    public_key = "ssh-rsa AAAA test-comment"
    requests_mock.get(f"{API_URL}/ssh/", json=[])
    requests_mock.post(f"{API_URL}/ssh/", json={"success": True})

    JarvisLabsAPIClient("token").add_ssh_key_if_needed(public_key)

    assert requests_mock.last_request.json() == {
        "ssh_key": public_key,
        "key_name": "dstack-36deb09319b2204c",
    }


def test_create_ssh_key_adds_key_and_returns_created_key_id(requests_mock):
    public_key = "ssh-rsa AAAA test-comment"
    requests_mock.post(f"{API_URL}/ssh/", json={"success": True})
    requests_mock.get(
        f"{API_URL}/ssh/",
        json=[
            {
                "ssh_key": "ssh-rsa AAAA another-comment",
                "key_name": "dstack-test-0.key",
                "key_id": "key-id",
            }
        ],
    )

    key_id = JarvisLabsAPIClient("token").create_ssh_key(
        public_key=public_key,
        key_name="dstack-test-0.key",
    )

    assert key_id == "key-id"
    assert requests_mock.request_history[0].json() == {
        "ssh_key": public_key,
        "key_name": "dstack-test-0.key",
    }


def test_create_ssh_key_raises_if_created_key_id_is_missing(requests_mock):
    requests_mock.post(f"{API_URL}/ssh/", json={"success": True})
    requests_mock.get(f"{API_URL}/ssh/", json=[])

    with pytest.raises(BackendError, match="Failed to find created JarvisLabs SSH key"):
        JarvisLabsAPIClient("token").create_ssh_key(
            public_key="ssh-rsa AAAA test-comment",
            key_name="dstack-test-0.key",
        )


def test_delete_ssh_key_deletes_key(requests_mock):
    requests_mock.delete(f"{API_URL}/ssh/key-id", json={"success": True})

    JarvisLabsAPIClient("token").delete_ssh_key("key-id")

    assert requests_mock.last_request.method == "DELETE"


def test_delete_ssh_key_ignores_missing_key(requests_mock):
    requests_mock.delete(f"{API_URL}/ssh/key-id", status_code=404, json={"detail": "not found"})

    JarvisLabsAPIClient("token").delete_ssh_key("key-id")


def test_create_gpu_vm_posts_to_regional_vm_endpoint(requests_mock):
    requests_mock.post(
        "https://backendn.jarvislabs.net/templates/vm/create",
        json={"machine_id": 123},
    )

    machine_id = JarvisLabsAPIClient("token").create_gpu_vm(
        gpu_type="A100-80GB",
        num_gpus=1,
        is_spot=False,
        storage=250,
        region="india-noida-01",
        name="dstack-test",
    )

    assert machine_id == "123"
    assert requests_mock.last_request.headers["Authorization"] == "Bearer token"
    assert requests_mock.last_request.json() == {
        "gpu_type": "A100-80GB",
        "num_gpus": 1,
        "hdd": 250,
        "region": "india-noida-01",
        "name": "dstack-test",
        "is_spot": False,
        "duration": "hour",
        "disk_type": "ssd",
        "http_ports": "",
        "script_id": None,
        "script_args": "",
        "fs_id": None,
        "arguments": "",
    }


def test_create_gpu_vm_posts_chennai_region_to_chennai_endpoint(requests_mock):
    requests_mock.post(
        "https://backendc.jarvislabs.net/templates/vm/create",
        json={"machine_id": 123},
    )

    JarvisLabsAPIClient("token").create_gpu_vm(
        gpu_type="RTX-PRO6000",
        num_gpus=1,
        is_spot=False,
        storage=100,
        region="india-chennai-01",
        name="dstack-test",
    )

    assert requests_mock.last_request.json()["gpu_type"] == "RTX-PRO6000"
    assert requests_mock.last_request.json()["region"] == "india-chennai-01"


def test_create_gpu_vm_rejects_unsupported_region(requests_mock):
    with pytest.raises(BackendError, match="Unsupported JarvisLabs region"):
        JarvisLabsAPIClient("token").create_gpu_vm(
            gpu_type="H100",
            num_gpus=1,
            is_spot=False,
            storage=100,
            region="unknown-region",
            name="dstack-test",
        )

    assert requests_mock.call_count == 0


def test_create_gpu_vm_sets_spot_flag(requests_mock):
    requests_mock.post(
        "https://backendn.jarvislabs.net/templates/vm/create",
        json={"machine_id": 123},
    )

    JarvisLabsAPIClient("token").create_gpu_vm(
        gpu_type="L4",
        num_gpus=1,
        is_spot=True,
        storage=100,
        region="india-noida-01",
        name="dstack-spot",
    )

    assert requests_mock.last_request.json()["is_spot"] is True


def test_create_cpu_vm_posts_to_regional_cpu_vm_endpoint(requests_mock):
    requests_mock.post(
        "https://backendn.jarvislabs.net/templates/vm/cpu/create",
        json={"machine_id": 456},
    )

    machine_id = JarvisLabsAPIClient("token").create_cpu_vm(
        vcpus=4,
        ram_gb=16,
        storage=100,
        region="india-noida-01",
        name="dstack-cpu",
    )

    assert machine_id == "456"
    assert requests_mock.last_request.json() == {
        "num_cpus": 1,
        "vcpus": 4,
        "ram_gb": 16,
        "hdd": 100,
        "region": "india-noida-01",
        "name": "dstack-cpu",
        "duration": "hour",
        "disk_type": "ssd",
    }


def test_destroy_instance_uses_cpu_vm_endpoint_for_cpu_vm(requests_mock):
    requests_mock.get(
        f"{API_URL}/users/fetch/456",
        json={
            "success": True,
            "instance": {
                "machine_id": 456,
                "template": "vm",
                "gpu_type": "CPU",
                "region": "india-noida-01",
            },
        },
    )
    requests_mock.post(
        "https://backendn.jarvislabs.net/templates/vm/cpu/destroy",
        json={"success": True},
    )

    JarvisLabsAPIClient("token").destroy_instance(machine_id="456", region="india-noida-01")

    assert requests_mock.last_request.qs == {"machine_id": ["456"]}


def test_is_cpu_vm_requires_vm_template_and_cpu_gpu_type():
    assert is_cpu_vm({"template": "vm", "gpu_type": "CPU"})
    assert is_cpu_vm({"framework": "VM", "gpu_type": "CPU"})
    assert not is_cpu_vm({"template": "pytorch", "gpu_type": "CPU"})
    assert not is_cpu_vm({"template": "vm", "gpu_type": "H100"})
