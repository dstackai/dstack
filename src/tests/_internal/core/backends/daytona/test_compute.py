import json
import shlex
from types import SimpleNamespace
from unittest.mock import patch

import gpuhunt
import pytest

from dstack._internal.core.backends.daytona.api_client import (
    API_URL,
    DaytonaAPIClient,
    DaytonaAPIError,
)
from dstack._internal.core.backends.daytona.compute import DaytonaCompute
from dstack._internal.core.backends.daytona.models import DaytonaConfig, DaytonaCreds
from dstack._internal.core.errors import ComputeError, NotYetTerminated, ProvisioningError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.instances import (
    InstanceAvailability,
    InstanceRuntime,
)
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.volumes import DaytonaVolumeConfiguration, VolumeMountPoint

COMPUTE_MODULE = "dstack._internal.core.backends.daytona.compute"
PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINOmx0T+hBRaJ6jCi21ZYe2NW3EZS8e0Mdwl+yZJt+kD project"
)
TOOLBOX_URL = "https://proxy.app.daytona.io/sandbox-id"
STARTUP_COMMANDS = ["install runner", "runner --key 'a key with spaces'"]


@pytest.fixture
def compute():
    with patch(f"{COMPUTE_MODULE}.DaytonaAPIClient", autospec=True) as client_class:
        compute = DaytonaCompute(DaytonaConfig(creds=DaytonaCreds(api_key="test-api-key")))
        client = client_class.return_value
        client.get_current_api_key.return_value = {"organizationId": "org-id"}
        client.get_organization_usage.return_value = {"regionUsage": [_cpu_usage(), _gpu_usage()]}
        client.get_available_sandbox_classes.return_value = [
            {"regionId": "us", "sandboxClass": "container", "gpuAvailable": False},
            {"regionId": "earth", "sandboxClass": "container", "gpuAvailable": True},
        ]
        client.create_sandbox.return_value = {"id": "sandbox-id", "state": "creating"}
        client.create_registry.return_value = {"id": "registry-id"}
        client.get_registries.return_value = []
        client.create_volume.return_value = {"id": "volume-id", "state": "pending_create"}
        client.get_volume.return_value = {"id": "volume-id", "state": "ready"}
        client.get_sandbox.return_value = {"id": "sandbox-id", "state": "started"}
        client.get_toolbox_url.return_value = TOOLBOX_URL
        client.get_session.return_value = {
            "sessionId": "dstack-runner",
            "commands": [{"id": "command-id", "command": "runner"}],
        }
        client.create_ssh_access.return_value = {
            "token": "ssh-token_123",
            "sshCommand": "ssh ssh-token_123@ssh.app.daytona.io -p 2222",
        }
        yield compute


def _cpu_usage(**overrides):
    return {
        "regionId": "us",
        "sandboxClass": "container",
        "totalCpuQuota": 100,
        "totalMemoryQuota": 200,
        "totalDiskQuota": 1000,
        "currentCpuUsage": 0,
        "currentMemoryUsage": 0,
        "currentDiskUsage": 0,
        "maxCpuPerSandbox": None,
        "maxMemoryPerSandbox": None,
        "maxDiskPerSandbox": None,
        **overrides,
    }


def _gpu_usage(**overrides):
    return {
        "regionId": "earth",
        "sandboxClass": "container",
        # GPU sandbox CPU/RAM/disk are not charged against these aggregate quotas.
        "totalCpuQuota": 0,
        "totalMemoryQuota": 0,
        "totalDiskQuota": 0,
        "currentCpuUsage": 0,
        "currentMemoryUsage": 0,
        "currentDiskUsage": 0,
        "totalGpuQuota": 4,
        "currentGpuUsage": 0,
        "maxCpuPerGpu": 16,
        "maxMemoryPerGpu": 192,
        "maxDiskPerGpu": 512,
        **overrides,
    }


def _item(*, gpu=False, spot=False, cpu=4, memory=16, disk=101, region=None):
    return gpuhunt.CatalogItem(
        provider="daytona",
        instance_name="test-shape",
        location=region or ("earth" if gpu else "us"),
        price=0.512345,
        cpu=cpu,
        memory=memory,
        disk_size=disk,
        gpu_count=2 if gpu else 0,
        gpu_name="RTXPRO6000" if gpu else None,
        gpu_vendor=gpuhunt.AcceleratorVendor.NVIDIA if gpu else None,
        gpu_memory=96 if gpu else None,
        spot=spot,
        provider_data={"gpu_type": "RTX-PRO-6000"} if gpu else {},
    )


def _offers(compute, *items):
    with patch.object(compute._catalog, "query", return_value=list(items)):
        return compute.get_offers_by_requirements(
            Requirements(resources=ResourcesSpec()),
            full_offers=False,
            unallocated_resources=False,
        )


def _run_job(compute, offer=None, instance_name="dstack-test-unique", **overrides):
    job_spec = SimpleNamespace(
        image_name="pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime",
        registry_auth=None,
        volumes=[],
    )
    for name in ("image_name", "registry_auth", "mount_points"):
        if name in overrides:
            setattr(job_spec, "volumes" if name == "mount_points" else name, overrides.pop(name))
    kwargs = {
        "run": SimpleNamespace(),
        "job": SimpleNamespace(job_spec=job_spec),
        "instance_offer": offer or _offers(compute, _item())[0],
        "project_ssh_public_key": PUBLIC_KEY,
        "project_ssh_private_key": "private-key",
        "volumes": [],
        "placement_group": None,
        "requirements": Requirements(resources=ResourcesSpec()),
        "extra_authorized_keys": [],
        **overrides,
    }
    with (
        patch(
            f"{COMPUTE_MODULE}.generate_unique_instance_name_for_job",
            return_value=instance_name,
        ),
        patch(f"{COMPUTE_MODULE}.get_docker_commands", return_value=list(STARTUP_COMMANDS)),
    ):
        return compute.run_job(**kwargs)


def _update(compute, data):
    compute.update_provisioning_data(data, PUBLIC_KEY, "private-key")


class TestRunJob:
    @pytest.mark.parametrize("gpu,spot", [(False, False), (True, False), (True, True)])
    def test_preserves_priced_resources_and_native_gpu_type(self, compute, gpu, spot):
        offer = _offers(compute, _item(gpu=gpu, spot=spot))[0]

        data = _run_job(compute, offer)

        payload = compute.api_client.create_sandbox.call_args.args[0]
        assert payload["name"] == "dstack-test-unique"
        assert payload["target"] == ("earth" if gpu else "us")
        assert (payload["cpu"], payload["memory"], payload["disk"]) == (4, 16, 101)
        assert payload["gpu"] == (2 if gpu else 0)
        assert payload["spot"] is spot
        if gpu:
            assert payload["gpuType"] == ["RTX-PRO-6000"]
        else:
            assert "gpuType" not in payload
        assert data.backend == BackendType.DAYTONA
        assert data.instance_id == "sandbox-id"
        assert data.price == offer.price == 0.512345
        assert data.instance_type.resources.disk.size_mib == 101 * 1024
        assert data.username == "root"
        assert data.dockerized is False
        assert data.hostname is None
        assert data.ssh_port is None
        compute.api_client.create_ssh_access.assert_not_called()
        compute.api_client.create_registry.assert_not_called()

    def test_creates_root_image_without_user_entrypoint_or_idle_shutdown(self, compute):
        data = _run_job(compute)

        payload = compute.api_client.create_sandbox.call_args.args[0]
        assert payload["buildInfo"]["dockerfileContent"] == (
            "FROM pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime\n"
            'USER root\nENTRYPOINT []\nCMD ["sleep", "infinity"]\n'
        )
        assert payload["user"] == "root"
        assert payload["public"] is False
        for field in ("autoStopInterval", "autoPauseInterval", "autoDeleteInterval", "ttlMinutes"):
            assert payload[field] == 0
        startup = json.loads(data.backend_data)["startup_command"]
        assert shlex.split(startup) == [
            "sh",
            "-c",
            " && ".join(STARTUP_COMMANDS),
        ]

    @pytest.mark.parametrize(
        "override",
        [
            {"image_name": "ubuntu:24.04\nRUN touch /injected"},
            {"image_name": ""},
        ],
    )
    def test_rejects_invalid_image_names_before_creating_sandbox(self, compute, override):
        with pytest.raises(ComputeError):
            _run_job(compute, **override)

        compute.api_client.create_sandbox.assert_not_called()

    @pytest.mark.parametrize("status_code", [None, 500])
    def test_lost_create_response_retains_unique_name_for_recovery_and_cleanup(
        self, compute, status_code
    ):
        compute.api_client.create_sandbox.side_effect = DaytonaAPIError(
            "response lost", status_code=status_code
        )

        data = _run_job(compute)

        assert data.instance_id == "dstack-test-unique"
        compute.api_client.create_sandbox.assert_called_once()
        _update(compute, data)
        compute.api_client.get_sandbox.assert_called_with("dstack-test-unique")
        compute.api_client.create_ssh_access.assert_called_once_with(
            "sandbox-id", expires_in_minutes=3650 * 24 * 60
        )
        with pytest.raises(NotYetTerminated):
            compute.terminate_instance(data.instance_id, data.region)
        compute.api_client.delete_sandbox.assert_called_once_with("dstack-test-unique")

    @pytest.mark.parametrize("status_code", [400, 429])
    def test_definite_create_failure_is_not_treated_as_success(self, compute, status_code):
        error = DaytonaAPIError("creation rejected", status_code=status_code)
        compute.api_client.create_sandbox.side_effect = error

        with pytest.raises(DaytonaAPIError) as exc_info:
            _run_job(compute)

        assert exc_info.value is error
        compute.api_client.create_sandbox.assert_called_once()


class TestRegistryAuth:
    @pytest.mark.parametrize(
        "image,registry,qualified",
        [
            ("org/private:v1", "docker.io", "docker.io/org/private:v1"),
            ("index.docker.io/org/private:v1", "docker.io", "docker.io/org/private:v1"),
            ("ghcr.io/org/image@sha256:abc", "ghcr.io", "ghcr.io/org/image@sha256:abc"),
            (
                "registry.example:5000/image:v1",
                "registry.example:5000",
                "registry.example:5000/image:v1",
            ),
        ],
    )
    def test_creates_job_registry_and_qualifies_private_base_image(
        self, compute, image, registry, qualified
    ):
        auth = RegistryAuth(username="registry-user", password="registry-password")
        data = _run_job(compute, image_name=image, registry_auth=auth)

        compute.api_client.create_registry.assert_called_once_with(
            {
                "name": "dstack-test-unique-registry",
                "url": registry,
                "username": auth.username,
                "password": auth.password,
            }
        )
        assert compute.api_client.create_sandbox.call_args.args[0]["buildInfo"][
            "dockerfileContent"
        ].startswith(f"FROM {qualified}\n")
        assert json.loads(data.backend_data)["registry_id"] == "registry-id"
        assert auth.password not in data.backend_data

    def test_keeps_separate_ids_for_jobs_with_the_same_registry_credentials(self, compute):
        auth = RegistryAuth(username="user", password="password")
        compute.api_client.create_registry.side_effect = [
            {"id": "registry-a"},
            {"id": "registry-b"},
        ]
        a = _run_job(compute, registry_auth=auth, instance_name="job-a")
        b = _run_job(compute, registry_auth=auth, instance_name="job-b")

        assert json.loads(a.backend_data)["registry_id"] == "registry-a"
        assert json.loads(b.backend_data)["registry_id"] == "registry-b"
        assert [c.args[0]["name"] for c in compute.api_client.create_registry.call_args_list] == [
            "job-a-registry",
            "job-b-registry",
        ]
        compute.api_client.get_sandbox.return_value = None
        compute.terminate_instance(a.instance_id, a.region, a.backend_data)
        compute.api_client.delete_registry.assert_called_once_with("registry-a")

    def test_recovers_only_own_registry_after_lost_create_response(self, compute):
        compute.api_client.create_registry.side_effect = DaytonaAPIError("response lost")
        compute.api_client.get_registries.return_value = [
            {"name": "someone-else", "id": "other-id"},
            {"name": "dstack-test-unique-registry", "id": "recovered-id"},
        ]

        data = _run_job(compute, registry_auth=RegistryAuth(username="user", password="password"))

        assert json.loads(data.backend_data)["registry_id"] == "recovered-id"
        compute.api_client.create_registry.assert_called_once()
        compute.api_client.delete_registry.assert_not_called()

    def test_registry_failure_does_not_create_a_sandbox_or_delete_existing_credentials(
        self, compute
    ):
        compute.api_client.create_registry.side_effect = DaytonaAPIError(
            "forbidden", status_code=403
        )

        with pytest.raises(DaytonaAPIError, match="forbidden"):
            _run_job(compute, registry_auth=RegistryAuth(username="user", password="password"))

        compute.api_client.create_sandbox.assert_not_called()
        compute.api_client.delete_registry.assert_not_called()

    def test_lost_sandbox_response_keeps_credentials_until_sandbox_is_gone(self, compute):
        compute.api_client.create_sandbox.side_effect = DaytonaAPIError("response lost")
        data = _run_job(compute, registry_auth=RegistryAuth(username="user", password="password"))

        with pytest.raises(NotYetTerminated):
            compute.terminate_instance(data.instance_id, data.region, data.backend_data)
        compute.api_client.delete_registry.assert_not_called()
        compute.api_client.get_sandbox.return_value = None
        compute.terminate_instance(data.instance_id, data.region, data.backend_data)
        compute.api_client.delete_registry.assert_called_once_with("registry-id")

    @pytest.mark.parametrize("cleanup_fails", [False, True])
    def test_registry_rollback_retries_transient_errors(
        self, compute, requests_mock, mocker, caplog, cleanup_fails
    ):
        offer = _offers(compute, _item())[0]
        compute.api_client = DaytonaAPIClient("test-api-key")
        mocker.patch("dstack._internal.core.backends.daytona.api_client.time.sleep")
        requests_mock.post(f"{API_URL}/docker-registry", json={"id": "registry-id"})
        requests_mock.post(
            f"{API_URL}/sandbox", status_code=400, json={"message": "invalid image"}
        )
        deletion = requests_mock.delete(
            f"{API_URL}/docker-registry/registry-id",
            [
                {"status_code": 503},
                {"status_code": 503 if cleanup_fails else 204},
            ],
        )

        with pytest.raises(DaytonaAPIError, match="invalid image") as exc:
            _run_job(
                compute,
                offer=offer,
                registry_auth=RegistryAuth(username="user", password="password"),
            )

        assert exc.value.status_code == 400
        assert deletion.call_count == (3 if cleanup_fails else 2)
        if cleanup_fails:
            assert "registry-id" in caplog.text
            assert "Delete it manually in Daytona" in caplog.text

    def test_registry_cleanup_survives_provisioning_and_server_restart(self, compute):
        data = _run_job(compute, registry_auth=RegistryAuth(username="user", password="password"))
        _update(compute, data)
        data = JobProvisioningData.model_validate_json(data.model_dump_json())
        assert json.loads(data.backend_data) == {
            "startup_command": None,
            "registry_id": "registry-id",
        }
        restarted = DaytonaCompute(compute.config)
        restarted.api_client = compute.api_client
        compute.api_client.get_sandbox.return_value = None
        compute.api_client.delete_registry.side_effect = [
            DaytonaAPIError("temporary outage"),
            None,
        ]

        with pytest.raises(DaytonaAPIError, match="temporary outage"):
            restarted.terminate_instance(data.instance_id, data.region, data.backend_data)
        restarted.terminate_instance(data.instance_id, data.region, data.backend_data)

        assert compute.api_client.delete_registry.call_count == 2


class TestVolumes:
    def test_mounts_selected_alternatives_and_multiple_volumes(self, compute):
        volumes = [
            SimpleNamespace(name="data", volume_id="data-id"),
            SimpleNamespace(name="cache", volume_id="cache-id"),
        ]
        _run_job(
            compute,
            volumes=volumes,
            mount_points=[
                VolumeMountPoint(name=["another-provider", "data"], path="/data"),
                VolumeMountPoint(name="cache", path="/cache"),
            ],
        )

        assert compute.api_client.create_sandbox.call_args.args[0]["volumes"] == [
            {"volumeId": "data-id", "mountPath": "/data"},
            {"volumeId": "cache-id", "mountPath": "/cache"},
        ]

    def test_creates_volume_without_a_size_or_region_and_waits_until_ready(self, compute):
        compute.api_client.get_volume.side_effect = [{"state": "creating"}, {"state": "ready"}]
        with (
            patch(f"{COMPUTE_MODULE}.generate_unique_volume_name", return_value="unique-volume"),
            patch(f"{COMPUTE_MODULE}.time.sleep") as sleep,
        ):
            data = compute.create_volume(SimpleNamespace())

        compute.api_client.create_volume.assert_called_once_with("unique-volume")
        sleep.assert_called_once_with(2)
        assert data.volume_id == "volume-id"
        assert data.size_gb is None
        assert data.price == 0
        assert data.attachable is False
        assert data.detachable is False

    def test_recovers_created_volume_by_name_after_lost_response(self, compute):
        compute.api_client.create_volume.side_effect = DaytonaAPIError("response lost")
        compute.api_client.get_volume_by_name.return_value = {"id": "recovered-id"}
        with patch(f"{COMPUTE_MODULE}.generate_unique_volume_name", return_value="unique-volume"):
            data = compute.create_volume(SimpleNamespace())

        assert data.volume_id == "recovered-id"
        compute.api_client.create_volume.assert_called_once()
        compute.api_client.get_volume_by_name.assert_called_once_with("unique-volume")

    def test_creation_timeout_is_bounded_and_cleans_up(self, compute):
        compute.api_client.get_volume.return_value = {"state": "creating"}
        with (
            patch(f"{COMPUTE_MODULE}.generate_unique_volume_name", return_value="unique-volume"),
            patch(f"{COMPUTE_MODULE}.time.monotonic", side_effect=[0, 61]),
        ):
            with pytest.raises(ComputeError, match="Timed out"):
                compute.create_volume(SimpleNamespace())
        compute.api_client.delete_volume.assert_called_once_with("volume-id")

    @pytest.mark.parametrize("cleanup_fails", [False, True])
    def test_volume_rollback_retries_transient_errors(
        self, compute, requests_mock, mocker, caplog, cleanup_fails
    ):
        compute.api_client = DaytonaAPIClient("test-api-key")
        mocker.patch("dstack._internal.core.backends.daytona.api_client.time.sleep")
        mocker.patch(f"{COMPUTE_MODULE}.generate_unique_volume_name", return_value="unique-volume")
        requests_mock.post(f"{API_URL}/volumes", json={"id": "volume-id"})
        requests_mock.get(
            f"{API_URL}/volumes/volume-id",
            json={"state": "error", "errorReason": "storage failed"},
        )
        deletion = requests_mock.delete(
            f"{API_URL}/volumes/volume-id",
            [
                {"status_code": 503},
                {"status_code": 503 if cleanup_fails else 204},
            ],
        )

        with pytest.raises(ComputeError, match="storage failed"):
            compute.create_volume(SimpleNamespace())

        assert deletion.call_count == (3 if cleanup_fails else 2)
        if cleanup_fails:
            assert "volume-id" in caplog.text
            assert "Delete it manually in Daytona" in caplog.text

    def test_registers_an_existing_volume_without_modifying_it(self, compute):
        volume = SimpleNamespace(configuration=DaytonaVolumeConfiguration(volume_id="external-id"))
        data = compute.register_volume(volume)

        assert data.volume_id == "external-id"
        compute.api_client.get_volume.assert_called_once_with("external-id")
        compute.api_client.create_volume.assert_not_called()
        compute.api_client.delete_volume.assert_not_called()

    @pytest.mark.parametrize("state", [None, {"state": "deleted"}, {"state": "error"}])
    def test_rejects_unusable_external_volume_without_deleting_it(self, compute, state):
        compute.api_client.get_volume.return_value = state
        volume = SimpleNamespace(configuration=DaytonaVolumeConfiguration(volume_id="external-id"))
        with pytest.raises(ComputeError):
            compute.register_volume(volume)
        compute.api_client.delete_volume.assert_not_called()

    def test_deletion_accepts_pending_request_without_repeating_delete(self, compute):
        compute.api_client.get_volume.side_effect = [
            {"state": "ready"},
            {"state": "pending_delete"},
            {"state": "deleting"},
            {"state": "deleted"},
            None,
        ]
        volume = SimpleNamespace(volume_id="volume-id")
        for _ in range(5):
            compute.delete_volume(volume)

        compute.api_client.delete_volume.assert_called_once_with("volume-id")


class TestUpdateProvisioningData:
    def test_queues_runner_and_returns_connection_data_once(self, compute):
        data = _run_job(compute)
        startup_command = json.loads(data.backend_data)["startup_command"]
        compute.api_client.get_session.return_value = None

        _update(compute, data)

        compute.api_client.create_session.assert_called_once_with(TOOLBOX_URL, "dstack-runner")
        compute.api_client.execute_session_command.assert_called_once_with(
            TOOLBOX_URL,
            "dstack-runner",
            startup_command,
            run_async=True,
        )
        assert data.hostname == "localhost"
        assert data.ssh_port == 10022
        assert data.ssh_proxy.hostname == "ssh.app.daytona.io"
        assert data.ssh_proxy.port == 2222
        assert data.ssh_proxy.username == "ssh-token_123"
        assert data.backend_data is None
        # Reconstruct the persisted state, as a new server process would do.
        data = JobProvisioningData.model_validate_json(data.model_dump_json())
        restarted = DaytonaCompute(compute.config)
        restarted.api_client = compute.api_client

        _update(restarted, data)
        _update(restarted, data)

        compute.api_client.get_session.assert_called_once()
        compute.api_client.execute_session_command.assert_called_once()
        compute.api_client.create_session.assert_called_once()
        compute.api_client.create_ssh_access.assert_called_once_with(
            "sandbox-id", expires_in_minutes=3650 * 24 * 60
        )

    def test_executes_an_existing_empty_session_after_interrupted_bootstrap(self, compute):
        data = _run_job(compute)
        compute.api_client.get_session.return_value = {
            "sessionId": "dstack-runner",
            "commands": [],
        }

        _update(compute, data)

        compute.api_client.create_session.assert_not_called()
        compute.api_client.execute_session_command.assert_called_once()
        compute.api_client.create_ssh_access.assert_called_once()
        assert data.hostname == "localhost"

    def test_recovers_existing_startup_after_server_restart_before_connection_data_saved(
        self, compute
    ):
        data = _run_job(compute)
        compute.api_client.get_session.side_effect = [
            None,
            {"commands": [{"id": "running", "command": "runner"}]},
        ]
        access = compute.api_client.create_ssh_access.return_value
        compute.api_client.create_ssh_access.side_effect = [
            DaytonaAPIError("response lost"),
            access,
        ]

        with pytest.raises(DaytonaAPIError, match="response lost"):
            _update(compute, data)
        assert data.hostname is None
        data = JobProvisioningData.model_validate_json(data.model_dump_json())
        restarted = DaytonaCompute(compute.config)
        restarted.api_client = compute.api_client

        _update(restarted, data)

        assert data.hostname == "localhost"
        compute.api_client.create_session.assert_called_once()
        compute.api_client.execute_session_command.assert_called_once()

    @pytest.mark.parametrize("sandbox", [None, {"id": "sandbox-id", "state": "building_snapshot"}])
    def test_waits_for_pending_or_not_yet_visible_sandbox(self, compute, sandbox):
        data = _run_job(compute)
        compute.api_client.get_sandbox.return_value = sandbox

        _update(compute, data)

        assert data.hostname is None
        compute.api_client.get_toolbox_url.assert_not_called()
        compute.api_client.create_ssh_access.assert_not_called()

    @pytest.mark.parametrize("state", ["error", "build_failed", "stopped", "destroying", "paused"])
    def test_reports_terminal_sandbox_failure(self, compute, state):
        data = _run_job(compute)
        compute.api_client.get_sandbox.return_value = {
            "id": "sandbox-id",
            "state": state,
            "errorReason": "image pull failed",
        }

        with pytest.raises(ProvisioningError, match="image pull failed"):
            _update(compute, data)

        compute.api_client.create_ssh_access.assert_not_called()

    @pytest.mark.parametrize("exit_code", [0, 1])
    def test_reports_exited_runner_setup_instead_of_executing_it_again(self, compute, exit_code):
        data = _run_job(compute)
        compute.api_client.get_session.return_value = {
            "commands": [{"id": "cmd", "command": "runner", "exitCode": exit_code}]
        }

        with pytest.raises(ProvisioningError, match=f"exited with code {exit_code}"):
            _update(compute, data)

        compute.api_client.execute_session_command.assert_not_called()
        compute.api_client.create_ssh_access.assert_not_called()

    @pytest.mark.parametrize("reverse", [False, True])
    def test_detects_exited_setup_regardless_of_session_command_order(self, compute, reverse):
        data = _run_job(compute)
        commands = [
            {"id": "failed", "command": "runner", "exitCode": 1},
            {"id": "running", "command": "diagnostic"},
        ]
        compute.api_client.get_session.return_value = {
            "commands": list(reversed(commands)) if reverse else commands
        }

        with pytest.raises(ProvisioningError, match="exited with code 1"):
            _update(compute, data)

        compute.api_client.execute_session_command.assert_not_called()

    def test_recovers_when_async_exec_response_is_lost(self, compute):
        data = _run_job(compute)
        compute.api_client.get_session.side_effect = [
            {"commands": []},
            {"commands": [{"id": "running", "command": "runner"}]},
        ]
        compute.api_client.execute_session_command.side_effect = DaytonaAPIError("response lost")

        with pytest.raises(DaytonaAPIError, match="response lost"):
            _update(compute, data)
        _update(compute, data)

        assert data.hostname == "localhost"
        compute.api_client.execute_session_command.assert_called_once()
        compute.api_client.create_ssh_access.assert_called_once()

    @pytest.mark.parametrize(
        "command",
        [
            "ssh ssh-token_123@ssh.app.daytona.io",  # Default SSH port is supported.
            "ssh -p 2222 ssh-token_123@ssh.app.daytona.io",
        ],
    )
    def test_accepts_native_ssh_command_argument_order(self, compute, command):
        data = _run_job(compute)
        compute.api_client.create_ssh_access.return_value["sshCommand"] = command

        _update(compute, data)

        assert data.ssh_proxy.port == (2222 if "-p" in command else 22)

    def test_uses_api_token_and_provider_supplied_ssh_gateway(self, compute):
        data = _run_job(compute)
        compute.api_client.create_ssh_access.return_value = {
            "token": "current-token",
            "sshCommand": "ssh previous-token@custom-gateway.example -p 2222",
        }

        _update(compute, data)

        assert data.ssh_proxy.username == "current-token"
        assert data.ssh_proxy.hostname == "custom-gateway.example"
        assert data.ssh_proxy.port == 2222

    @pytest.mark.parametrize(
        "command",
        [
            "ssh ssh.app.daytona.io",
            "ssh ssh-token_123@",
            "ssh ssh-token_123@ssh.app.daytona.io -p 0",
            "ssh ssh-token_123@ssh.app.daytona.io -p 70000",
            "ssh ssh-token_123@ssh.app.daytona.io -p invalid",
            "echo ssh-token_123@ssh.app.daytona.io",
        ],
    )
    def test_rejects_invalid_native_ssh_details(self, compute, command):
        data = _run_job(compute)
        compute.api_client.create_ssh_access.return_value["sshCommand"] = command

        with pytest.raises(ProvisioningError, match="invalid SSH connection details"):
            _update(compute, data)

        assert data.hostname is None

    def test_rejects_missing_ssh_token(self, compute):
        data = _run_job(compute)
        del compute.api_client.create_ssh_access.return_value["token"]

        with pytest.raises(ProvisioningError, match="invalid SSH connection details"):
            _update(compute, data)

        assert data.hostname is None


class TestTerminateInstance:
    def test_deletion_is_idempotent_while_provider_is_destroying(self, compute):
        compute.api_client.get_sandbox.side_effect = [
            {"state": "started"},
            {"state": "destroying"},
            {"state": "destroyed"},
            None,
        ]

        for _ in range(2):
            with pytest.raises(NotYetTerminated):
                compute.terminate_instance("sandbox-id", "us")
        compute.terminate_instance("sandbox-id", "us")
        compute.terminate_instance("sandbox-id", "us")

        compute.api_client.delete_sandbox.assert_called_once_with("sandbox-id")


class TestGetOffersByRequirements:
    def test_offer_queries_use_only_api_key_accessible_endpoints(self, requests_mock):
        # Organization details require dashboard authentication, even for a valid API key.
        # No organization-details mock is registered so using that endpoint fails this test.
        paths = [
            "/api-keys/current",
            "/organizations/org-id/usage",
            "/organizations/org-id/available-sandbox-classes",
        ]
        requests_mock.get(API_URL + paths[0], json={"organizationId": "org-id"})
        requests_mock.get(API_URL + paths[1], json={"regionUsage": [_cpu_usage(), _gpu_usage()]})
        requests_mock.get(
            API_URL + paths[2],
            json=[
                {"regionId": "us", "sandboxClass": "container", "gpuAvailable": False},
                {"regionId": "earth", "sandboxClass": "container", "gpuAvailable": True},
            ],
        )
        compute = DaytonaCompute(DaytonaConfig(creds=DaytonaCreds(api_key="test-api-key")))

        offers = _offers(compute, _item(), _item(gpu=True))

        assert [offer.availability for offer in offers] == [InstanceAvailability.AVAILABLE] * 2
        assert [request.url for request in requests_mock.request_history] == [
            API_URL + path for path in paths
        ]
        assert all(
            request.headers["Authorization"] == "Bearer test-api-key"
            for request in requests_mock.request_history
        )

    def test_cpu_and_gpu_offers_retain_native_metadata_and_runner_runtime(self, compute):
        offers = _offers(compute, _item(), _item(gpu=True))

        assert [offer.availability for offer in offers] == [InstanceAvailability.AVAILABLE] * 2
        assert all(offer.instance_runtime == InstanceRuntime.RUNNER for offer in offers)
        assert offers[1].backend_data == {"gpu_type": "RTX-PRO-6000"}
        assert len(offers[1].instance.resources.gpus) == 2
        assert offers[1].instance.resources.gpus[0].name == "RTXPRO6000"

    def test_organization_id_is_cached_but_quotas_are_refreshed(self, compute):
        assert _offers(compute, _item())[0].availability == InstanceAvailability.AVAILABLE
        compute.api_client.get_organization_usage.return_value["regionUsage"] = [
            _cpu_usage(currentCpuUsage=100)
        ]

        assert _offers(compute, _item())[0].availability == InstanceAvailability.NO_QUOTA
        compute.api_client.get_current_api_key.assert_called_once_with()
        assert compute.api_client.get_organization_usage.call_count == 2

    def test_skips_quota_calls_without_catalog_offers(self, compute):
        assert _offers(compute) == []

        compute.api_client.get_current_api_key.assert_not_called()
        compute.api_client.get_organization_usage.assert_not_called()

    def test_filters_configured_regions(self, compute):
        compute.config.regions = ["earth"]

        offers = _offers(compute, _item(), _item(gpu=True))

        assert [offer.region for offer in offers] == ["earth"]

    @pytest.mark.parametrize("resource", ["Cpu", "Memory", "Disk"])
    def test_cpu_aggregate_quotas_include_current_usage(self, compute, resource):
        compute.api_client.get_organization_usage.return_value["regionUsage"] = [
            _cpu_usage(**{f"current{resource}Usage": 999})
        ]

        assert _offers(compute, _item())[0].availability == InstanceAvailability.NO_QUOTA

    @pytest.mark.parametrize("resource", ["Cpu", "Memory", "Disk"])
    def test_cpu_region_per_sandbox_limit_is_enforced(self, compute, resource):
        compute.api_client.get_organization_usage.return_value["regionUsage"] = [
            _cpu_usage(**{f"max{resource}PerSandbox": 1})
        ]

        assert _offers(compute, _item())[0].availability == InstanceAvailability.NO_QUOTA

    def test_cpu_unknown_per_sandbox_limits_use_known_aggregate_quota(self, compute):
        assert (
            _offers(compute, _item(cpu=90, memory=190, disk=999))[0].availability
            == InstanceAvailability.AVAILABLE
        )

    def test_ignores_other_sandbox_classes_when_checking_usage(self, compute):
        compute.api_client.get_organization_usage.return_value["regionUsage"].append(
            _cpu_usage(sandboxClass="windows", totalCpuQuota=0)
        )
        compute.api_client.get_available_sandbox_classes.return_value.append(
            {"regionId": "earth", "sandboxClass": "windows", "gpuAvailable": False}
        )

        assert _offers(compute, _item())[0].availability == InstanceAvailability.AVAILABLE
        assert _offers(compute, _item(gpu=True))[0].availability == InstanceAvailability.AVAILABLE

    @pytest.mark.parametrize("missing", ["usage", "sandbox_class"])
    def test_region_requires_both_quota_and_container_class(self, compute, missing):
        if missing == "usage":
            compute.api_client.get_organization_usage.return_value["regionUsage"] = []
        else:
            compute.api_client.get_available_sandbox_classes.return_value = []

        assert _offers(compute, _item())[0].availability == InstanceAvailability.NO_QUOTA

    @pytest.mark.parametrize("spot", [False, True])
    @pytest.mark.parametrize("total,used", [(4, 3), (0, 0)])
    def test_gpu_quota_uses_remaining_count_only_for_on_demand(self, compute, spot, total, used):
        compute.api_client.get_organization_usage.return_value["regionUsage"] = [
            _gpu_usage(totalGpuQuota=total, currentGpuUsage=used)
        ]

        expected = InstanceAvailability.AVAILABLE if spot else InstanceAvailability.NO_QUOTA
        assert _offers(compute, _item(gpu=True, spot=spot))[0].availability == expected

    @pytest.mark.parametrize(
        "allowed,expected",
        [
            (None, InstanceAvailability.AVAILABLE),
            ([], InstanceAvailability.NO_QUOTA),
            (["RTX-PRO-6000"], InstanceAvailability.AVAILABLE),
            (["H100"], InstanceAvailability.NO_QUOTA),
        ],
    )
    @pytest.mark.parametrize("source", ["usage", "sandbox_class"])
    @pytest.mark.parametrize("spot", [False, True])
    def test_gpu_allowlist_uses_api_gpu_name(self, compute, allowed, expected, source, spot):
        if source == "usage":
            compute.api_client.get_organization_usage.return_value["regionUsage"] = [
                _gpu_usage(allowedGpuTypes=allowed)
            ]
        else:
            compute.api_client.get_available_sandbox_classes.return_value[1]["allowedGpuTypes"] = (
                allowed
            )

        assert _offers(compute, _item(gpu=True, spot=spot))[0].availability == expected

    @pytest.mark.parametrize("shape", [{"cpu": 33}, {"memory": 385}, {"disk": 1025}])
    @pytest.mark.parametrize("spot", [False, True])
    def test_gpu_resource_limit_is_multiplied_by_gpu_count(self, compute, shape, spot):
        boundary = {name: value - 1 for name, value in shape.items()}

        assert (
            _offers(compute, _item(gpu=True, spot=spot, **boundary))[0].availability
            == InstanceAvailability.AVAILABLE
        )
        assert (
            _offers(compute, _item(gpu=True, spot=spot, **shape))[0].availability
            == InstanceAvailability.NO_QUOTA
        )

    @pytest.mark.parametrize("resource", ["Cpu", "Memory", "Disk"])
    def test_gpu_null_limit_falls_back_to_absolute_region_per_sandbox_limit(
        self, compute, resource
    ):
        usage = _gpu_usage(**{f"max{resource}PerGpu": None})
        sizes = {"Cpu": 4, "Memory": 16, "Disk": 101}
        usage[f"max{resource}PerSandbox"] = sizes[resource] - 1
        compute.api_client.get_organization_usage.return_value["regionUsage"] = [usage]

        assert _offers(compute, _item(gpu=True))[0].availability == InstanceAvailability.NO_QUOTA

    def test_gpu_unknown_resource_limits_do_not_impose_guessed_global_defaults(self, compute):
        compute.api_client.get_organization_usage.return_value["regionUsage"] = [
            _gpu_usage(maxCpuPerGpu=None, maxMemoryPerGpu=None, maxDiskPerGpu=None)
        ]

        assert (
            _offers(compute, _item(gpu=True, cpu=32, memory=384, disk=1024))[0].availability
            == InstanceAvailability.AVAILABLE
        )

    @pytest.mark.parametrize("spot", [False, True])
    def test_gpu_class_must_allow_gpu(self, compute, spot):
        compute.api_client.get_available_sandbox_classes.return_value[1]["gpuAvailable"] = False

        assert (
            _offers(compute, _item(gpu=True, spot=spot))[0].availability
            == InstanceAvailability.NO_QUOTA
        )
