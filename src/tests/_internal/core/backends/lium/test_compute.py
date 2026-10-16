import json
import shlex
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gpuhunt
import paramiko
import pytest

from dstack._internal.core.backends.lium.api_client import LiumAPIError
from dstack._internal.core.backends.lium.compute import (
    LiumCompute,
    LiumInstanceBackendData,
    _bootstrap_runner,
    _get_bootstrap_command,
    _get_image_env_and_cwd_command,
    _get_provider_ssh,
)
from dstack._internal.core.backends.lium.models import LiumConfig, LiumCreds
from dstack._internal.core.errors import (
    ComputeError,
    NoCapacityError,
    NotYetTerminated,
    ProvisioningError,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.common import RegistryAuth
from dstack._internal.core.models.instances import InstanceAvailability, InstanceRuntime
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import JobProvisioningData, Requirements
from dstack._internal.core.models.unix import UnixUser
from dstack._internal.utils.crypto import generate_rsa_key_pair_bytes

COMPUTE_MODULE = "dstack._internal.core.backends.lium.compute"
PUBLIC_KEY = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINOmx0T+hBRaJ6jCi21ZYe2NW3EZS8e0Mdwl+yZJt+kD project"
)
STARTUP_COMMANDS = ["install runner", "runner --key 'a key with spaces'"]


@pytest.fixture
def compute():
    with patch(f"{COMPUTE_MODULE}.LiumAPIClient", autospec=True) as client_class:
        compute = LiumCompute(LiumConfig(creds=LiumCreds(api_key="test-api-key")))
        client = client_class.return_value
        client.create_template.return_value = {"id": "template-id"}
        client.create_docker_credential.return_value = {"id": "credential-id"}
        client.rent_executor.return_value = {"success": True, "pod_id": "pod-id"}
        client.get_pod.return_value = _pod()
        client.get_pods.return_value = []
        client.get_account_events.return_value = []
        client.get_version.return_value = {"features": ["rent_idempotency"]}
        client.get_templates.return_value = []
        yield compute


def _pod(**overrides):
    return {
        "id": "pod-id",
        "pod_name": "dstack-test-unique",
        "executor_id": "executor-id",
        "status": "RUNNING",
        "ssh_connect_cmd": "ssh root@192.0.2.10 -p 40022",
        "ports_mapping": {"22": 40022, "10022": 40100},
        **overrides,
    }


def _item():
    return gpuhunt.CatalogItem(
        provider="lium",
        instance_name="executor-id",
        location="us-ia",
        price=0.42,
        cpu=6,
        memory=42,
        disk_size=100,
        gpu_count=1,
        gpu_name="A6000",
        gpu_vendor=gpuhunt.AcceleratorVendor.NVIDIA,
        gpu_memory=48,
        spot=False,
        provider_data={"rent_url": "https://lium.io/browse-pods/executor-id"},
    )


def _offer(compute):
    with patch.object(compute._catalog, "query", return_value=[_item()]):
        return compute.get_offers_by_requirements(
            Requirements(resources=ResourcesSpec()),
            full_offers=False,
            unallocated_resources=False,
        )[0]


def _run_job(compute, **overrides):
    job_spec = SimpleNamespace(
        image_name="pytorch/pytorch:2.11.0-cuda12.8-cudnn9-runtime",
        registry_auth=None,
        volumes=[],
        user=None,
    )
    for name in ("image_name", "registry_auth", "user", "mount_points"):
        if name in overrides:
            setattr(job_spec, "volumes" if name == "mount_points" else name, overrides.pop(name))
    kwargs = {
        "run": SimpleNamespace(),
        "job": SimpleNamespace(job_spec=job_spec),
        "instance_offer": _offer(compute),
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
            return_value="dstack-test-unique",
        ),
        patch(f"{COMPUTE_MODULE}.get_docker_commands", return_value=list(STARTUP_COMMANDS)),
    ):
        return compute.run_job(**kwargs)


def _update(compute, data):
    compute.update_provisioning_data(data, PUBLIC_KEY, "private-key")


def _terminate(compute, data):
    compute.terminate_instance(data.instance_id, data.region, data.backend_data)


class TestRunJob:
    def test_uses_offer_and_configures_root_ssh_bootstrap(self, compute):
        offer = _offer(compute)
        user = UnixUser.parse("10001:10001")

        data = _run_job(compute, instance_offer=offer, user=user)

        assert offer.availability == InstanceAvailability.AVAILABLE
        assert offer.instance_runtime == InstanceRuntime.RUNNER
        assert data.backend == BackendType.LIUM
        assert data.instance_id == "pod-id"
        assert data.price == 0.42
        assert data.instance_type.resources.memory_mib == 42 * 1024
        assert data.username == "root"
        assert data.dockerized is False
        assert data.hostname is None
        assert data.ssh_port is None
        template = compute.api_client.create_template.call_args.args[0]
        assert template["entrypoint"] == "/bin/sh"
        assert shlex.split(template["startup_commands"]) == ["-c", "exec sleep infinity"]
        assert template["internal_ports"] == [22, 10022]
        assert template["supports_volume_encryption"] is False
        assert "user" not in template
        executor, payload, key = compute.api_client.rent_executor.call_args.args
        assert executor == "executor-id"
        assert payload["gpu_count"] == 1
        assert payload["template_id"] == "template-id"
        assert payload["user_public_key"] == PUBLIC_KEY
        assert payload["enable_volume_encryption"] is False
        assert "termination_hours" not in payload
        assert key
        backend = LiumInstanceBackendData.model_validate_json(data.backend_data)
        assert backend.rent_payload is None
        assert backend.startup_command == " && ".join(STARTUP_COMMANDS)

    @pytest.mark.parametrize(
        "image",
        ["ubuntu", "registry.example:5000/team/image:tag", "registry.example/image@sha256:abcd"],
    )
    def test_passes_full_image_reference_using_sdk_convention(self, compute, image):
        _run_job(compute, image_name=image)

        template = compute.api_client.create_template.call_args.args[0]
        assert template["docker_image"] == image
        assert template["docker_image_tag"] == ""
        assert template["docker_image_digest"] == ""

    def test_private_registry_credentials_are_selected_and_not_stored(self, compute):
        data = _run_job(
            compute, registry_auth=RegistryAuth(username="user", password="secret-password")
        )

        compute.api_client.create_docker_credential.assert_called_once_with(
            {"docker_username": "user", "docker_password": "secret-password"}
        )
        template = compute.api_client.create_template.call_args.args[0]
        assert template["docker_credential_id"] == "credential-id"
        assert "secret-password" not in data.backend_data
        assert json.loads(data.backend_data)["credential_id"] == "credential-id"

    def test_uncertain_credential_creation_never_recovers_by_username(self, compute):
        compute.api_client.create_docker_credential.side_effect = LiumAPIError("timeout")

        with pytest.raises(ComputeError, match="Check Docker credentials"):
            _run_job(compute, registry_auth=RegistryAuth(username="user", password="secret"))

        compute.api_client.delete_docker_credential.assert_not_called()
        compute.api_client.create_template.assert_not_called()
        compute.api_client.rent_executor.assert_not_called()

    def test_recovers_lost_template_response_by_unique_name(self, compute):
        compute.api_client.create_template.side_effect = LiumAPIError("timeout")
        compute.api_client.get_templates.return_value = [
            {"id": "someone-elses-template", "name": "other"},
            {"id": "recovered-template", "name": "dstack-test-unique"},
        ]

        data = _run_job(compute)

        assert json.loads(data.backend_data)["template_id"] == "recovered-template"
        assert compute.api_client.rent_executor.call_args.args[1]["template_id"] == (
            "recovered-template"
        )

    def test_template_failure_cleans_up_owned_credential(self, compute):
        compute.api_client.create_template.side_effect = LiumAPIError("bad image", 400)

        with pytest.raises(LiumAPIError):
            _run_job(compute, registry_auth=RegistryAuth(username="user", password="secret"))

        compute.api_client.delete_docker_credential.assert_called_once_with("credential-id")
        compute.api_client.rent_executor.assert_not_called()

    def test_capacity_failure_cleans_up_template_then_credential(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError(
            "unavailable", 409, "node_paused_by_provider"
        )
        cleanup = Mock()
        cleanup.attach_mock(compute.api_client.delete_template, "template")
        cleanup.attach_mock(compute.api_client.delete_docker_credential, "credential")

        with pytest.raises(NoCapacityError):
            _run_job(compute, registry_auth=RegistryAuth(username="user", password="secret"))

        assert [call[0] for call in cleanup.mock_calls] == ["template", "credential"]

    def test_uncertain_rent_retains_cleanup_ids_and_original_request(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")

        data = _run_job(compute)

        assert data.instance_id == "dstack-test-unique"
        backend = LiumInstanceBackendData.model_validate_json(data.backend_data)
        assert backend.template_id == "template-id"
        assert backend.rent_payload == compute.api_client.rent_executor.call_args.args[1]
        assert backend.idempotency_key == compute.api_client.rent_executor.call_args.args[2]
        compute.api_client.delete_template.assert_not_called()


class TestUpdateProvisioningData:
    @pytest.mark.parametrize("state", ["PENDING", "CREATING", "PULLING"])
    def test_waits_for_running_pod(self, compute, state):
        data = _run_job(compute)
        compute.api_client.get_pod.return_value = _pod(status=state)

        with patch(f"{COMPUTE_MODULE}._bootstrap_runner") as bootstrap:
            _update(compute, data)

        bootstrap.assert_not_called()
        assert data.hostname is None

    @pytest.mark.parametrize("state", ["FAILED", "STOPPED", "CREATION_FAILED", "DELETING"])
    def test_terminal_state_fails_provisioning(self, compute, state):
        data = _run_job(compute)
        compute.api_client.get_pod.return_value = _pod(status=state)

        with pytest.raises(ProvisioningError, match=state):
            _update(compute, data)

    def test_sets_direct_runner_ssh_after_bootstrap(self, compute):
        data = _run_job(compute)

        with patch(f"{COMPUTE_MODULE}._bootstrap_runner") as bootstrap:
            _update(compute, data)

        ssh, key, command = bootstrap.call_args.args
        assert (ssh.hostname, ssh.port, ssh.username) == ("192.0.2.10", 40022, "root")
        assert key == "private-key"
        assert command == " && ".join(STARTUP_COMMANDS)
        assert (data.hostname, data.ssh_port) == ("192.0.2.10", 40100)
        assert data.ssh_proxy is None

    def test_uses_provider_proxy_when_runner_port_is_not_mapped(self, compute):
        data = _run_job(compute)
        compute.api_client.get_pod.return_value = _pod(ports_mapping={"22": 40022})

        with patch(f"{COMPUTE_MODULE}._bootstrap_runner"):
            _update(compute, data)

        assert (data.hostname, data.ssh_port) == ("localhost", 10022)
        assert (data.ssh_proxy.hostname, data.ssh_proxy.port) == ("192.0.2.10", 40022)

    def test_running_does_not_imply_provider_ssh_is_ready(self, compute):
        data = _run_job(compute)

        with patch(f"{COMPUTE_MODULE}._bootstrap_runner", side_effect=paramiko.SSHException()):
            _update(compute, data)

        assert data.hostname is None

    def test_recovers_uncertain_rent_without_replaying_if_pod_exists(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)
        compute.api_client.get_pods.return_value = [
            _pod(id="unrelated", executor_id="wrong-executor"),
            _pod(),
        ]

        with patch(f"{COMPUTE_MODULE}._bootstrap_runner"):
            _update(compute, data)

        assert data.instance_id == "pod-id"
        assert json.loads(data.backend_data)["rent_payload"] is None
        assert compute.api_client.rent_executor.call_count == 1

    def test_replays_exact_request_and_key_only_during_provisioning(self, compute):
        compute.api_client.rent_executor.side_effect = [
            LiumAPIError("timeout"),
            {"success": True, "pod_id": "pod-id"},
        ]
        data = _run_job(compute)

        with patch(f"{COMPUTE_MODULE}._bootstrap_runner"):
            _update(compute, data)

        first, second = compute.api_client.rent_executor.call_args_list
        assert first == second
        assert data.instance_id == "pod-id"

    def test_definitive_replay_failure_can_be_terminated_without_rerenting(self, compute):
        compute.api_client.rent_executor.side_effect = [
            LiumAPIError("timeout"),
            LiumAPIError("unavailable", 400, "node_unavailable", idempotent_replayed=True),
        ]
        data = _run_job(compute)

        _update(compute, data)
        # The server only saves the result when update_provisioning_data returns.
        # A later failing call must not be needed to persist the definitive outcome.
        persisted = data.model_dump_json()
        next_poll = JobProvisioningData.model_validate_json(persisted)
        with pytest.raises(ProvisioningError, match="rental failed"):
            _update(compute, next_poll)
        _terminate(compute, JobProvisioningData.model_validate_json(persisted))

        assert json.loads(data.backend_data)["rent_failed"] is True
        assert compute.api_client.rent_executor.call_count == 2
        compute.api_client.delete_pod.assert_not_called()

    @pytest.mark.parametrize("status", [401, 403, 422, 429])
    def test_unrecorded_replay_rejection_keeps_original_rental_uncertain(self, compute, status):
        compute.api_client.rent_executor.side_effect = [
            LiumAPIError("timeout"),
            LiumAPIError("rejected before idempotency", status),
        ]
        data = _run_job(compute)
        original_backend_data = data.backend_data

        _update(compute, data)

        assert data.backend_data == original_backend_data
        assert compute.api_client.rent_executor.call_count == 2
        compute.api_client.delete_template.assert_not_called()
        compute.api_client.delete_docker_credential.assert_not_called()

    def test_expired_idempotency_key_is_never_replayed(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)
        backend = LiumInstanceBackendData.model_validate_json(data.backend_data)
        backend.rent_started_at = datetime.now(timezone.utc) - timedelta(days=1)
        data.backend_data = backend.model_dump_json()

        _update(compute, data)

        assert compute.api_client.rent_executor.call_count == 1
        compute.api_client.get_version.assert_not_called()
        compute.api_client.delete_template.assert_not_called()

    def test_backend_without_idempotency_feature_is_not_retried(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        compute.api_client.get_version.return_value = {"features": []}
        data = _run_job(compute)

        _update(compute, data)

        assert compute.api_client.rent_executor.call_count == 1
        compute.api_client.delete_template.assert_not_called()


class TestTerminateInstance:
    def test_keeps_cleanup_resources_until_pod_disappears(self, compute):
        data = _run_job(compute, registry_auth=RegistryAuth(username="user", password="secret"))

        with pytest.raises(NotYetTerminated):
            _terminate(compute, data)

        compute.api_client.delete_pod.assert_called_once_with("pod-id")
        compute.api_client.delete_template.assert_not_called()
        compute.api_client.delete_docker_credential.assert_not_called()
        compute.api_client.get_pod.return_value = None
        _terminate(compute, data)
        compute.api_client.delete_template.assert_called_once_with("template-id")
        compute.api_client.delete_docker_credential.assert_called_once_with("credential-id")

    def test_deleting_state_does_not_repeat_delete(self, compute):
        data = _run_job(compute)
        compute.api_client.get_pod.return_value = _pod(status="DELETING")

        with pytest.raises(NotYetTerminated):
            _terminate(compute, data)

        compute.api_client.delete_pod.assert_not_called()

    def test_reconciles_delete_state_conflict(self, compute):
        data = _run_job(compute)
        compute.api_client.get_pod.side_effect = [_pod(), _pod(status="DELETING")]
        compute.api_client.delete_pod.side_effect = LiumAPIError(
            "conflict", 400, "pod_state_conflict"
        )

        with pytest.raises(NotYetTerminated):
            _terminate(compute, data)

        compute.api_client.delete_template.assert_not_called()

    def test_uncertain_outcome_never_rerents_during_termination(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)

        with pytest.raises(NotYetTerminated, match="uncertain"):
            _terminate(compute, data)

        assert compute.api_client.rent_executor.call_count == 1
        compute.api_client.delete_template.assert_not_called()
        compute.api_client.delete_pod.assert_not_called()

    def test_uncertain_rental_found_by_name_is_deleted(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)
        compute.api_client.get_pods.return_value = [_pod()]

        with pytest.raises(NotYetTerminated):
            _terminate(compute, data)

        compute.api_client.delete_pod.assert_called_once_with("pod-id")

    @pytest.mark.parametrize(
        "deleted_event", [{"to_status": "DELETED"}, {"sub_event_type": "pod-delete.success"}]
    )
    def test_deleted_rental_is_recovered_from_durable_account_events(self, compute, deleted_event):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)
        compute.api_client.get_pods.return_value = [_pod()]
        with pytest.raises(NotYetTerminated):
            _terminate(compute, data)
        # A fresh backend receives exactly the same persisted data. The deleted
        # pod is no longer listed, but its account event still identifies it.
        compute.api_client.get_pods.return_value = []
        compute.api_client.get_pod.return_value = None
        compute.api_client.get_account_events.return_value = [
            {"pod_id": "pod-id", "pod_name": "dstack-test-unique", **deleted_event}
        ]
        next_compute = LiumCompute(compute.config)

        _terminate(next_compute, JobProvisioningData.model_validate_json(data.model_dump_json()))

        compute.api_client.get_pod.assert_called_once_with("pod-id")
        compute.api_client.delete_template.assert_called_once_with("template-id")
        assert compute.api_client.rent_executor.call_count == 1

    def test_unrelated_events_do_not_resolve_uncertain_outcome(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)
        compute.api_client.get_account_events.return_value = [
            {"pod_id": "other-id", "pod_name": "other-pod", "to_status": "DELETED"}
        ]

        with pytest.raises(NotYetTerminated, match="uncertain"):
            _terminate(compute, data)

        compute.api_client.get_pod.assert_not_called()
        compute.api_client.delete_template.assert_not_called()

    def test_creation_event_without_visible_pod_is_not_proof_of_deletion(self, compute):
        compute.api_client.rent_executor.side_effect = LiumAPIError("timeout")
        data = _run_job(compute)
        compute.api_client.get_pod.return_value = None
        compute.api_client.get_account_events.return_value = [
            {"pod_id": "pod-id", "pod_name": "dstack-test-unique", "to_status": "PENDING"}
        ]

        with pytest.raises(NotYetTerminated, match="uncertain"):
            _terminate(compute, data)

        compute.api_client.delete_template.assert_not_called()


class TestBootstrapRunner:
    def test_accepts_server_generated_pkcs8_project_key(self):
        # Real key generation/conversion earns its subprocess cost here: mocking
        # pkey_from_str hid incompatibility with the server's actual PKCS8 format.
        private_key, public_key = generate_rsa_key_pair_bytes()
        assert private_key.startswith(b"-----BEGIN PRIVATE KEY-----")
        with patch(f"{COMPUTE_MODULE}.paramiko.SSHClient") as ssh_class:
            client = ssh_class.return_value.__enter__.return_value
            stdout = Mock()
            stdout.read.return_value = b"running"
            stdout.channel.recv_exit_status.return_value = 0
            client.exec_command.return_value = (Mock(), stdout, Mock())

            _bootstrap_runner(_get_provider_ssh(_pod()), private_key.decode(), "runner")

            pkey = client.connect.call_args.kwargs["pkey"]
            assert pkey.get_name() == "ssh-rsa"
            assert pkey.get_base64() == public_key.decode().split()[1]

    def test_private_bootstrap_does_not_restrict_runner_created_files(self, tmp_path):
        # Execute the generated shell so a restrictive inherited umask cannot
        # silently break non-root access to runner-created job/SSH files.
        directory = tmp_path / "bootstrap"
        job_directory = tmp_path / "job"
        startup = f"mkdir {shlex.quote(str(job_directory))} && touch {job_directory}/key"
        with (
            patch(f"{COMPUTE_MODULE}.BOOTSTRAP_DIR", str(directory)),
            patch(
                f"{COMPUTE_MODULE}._get_image_env_and_cwd_command",
                side_effect=lambda path: shlex.join(["/bin/sh", path]),
            ),
        ):
            command = shlex.split(_get_bootstrap_command(startup))
        # The production command detaches; join the immediate shell child in this
        # test instead of polling or sleeping for the exit marker.
        command[-1] += "\nwait"

        subprocess.run(command, capture_output=True, check=True, timeout=5)

        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert stat.S_IMODE((directory / "runner.sh").stat().st_mode) == 0o600
        assert stat.S_IMODE(job_directory.stat().st_mode) == 0o755
        assert stat.S_IMODE((job_directory / "key").stat().st_mode) == 0o644
        assert (directory / "exit-code").read_text() == "0\n"

    @pytest.mark.parametrize("output,status", [(b"running", 0), (b"exited", 0), (b"", 1)])
    def test_checks_existing_bootstrap_status(self, output, status):
        ssh = _get_provider_ssh(_pod())
        with (
            patch(f"{COMPUTE_MODULE}.paramiko.SSHClient") as ssh_class,
            patch(f"{COMPUTE_MODULE}.pkey_from_str", return_value="parsed-key"),
        ):
            client = ssh_class.return_value.__enter__.return_value
            stdout = Mock()
            stdout.read.return_value = output
            stdout.channel.recv_exit_status.return_value = status
            client.exec_command.return_value = (Mock(), stdout, Mock())
            if output == b"running":
                _bootstrap_runner(ssh, "private-key", "runner")
            else:
                with pytest.raises(ProvisioningError):
                    _bootstrap_runner(ssh, "private-key", "runner")
            assert client.connect.call_args.kwargs["allow_agent"] is False
            assert client.connect.call_args.kwargs["look_for_keys"] is False
            assert client.connect.call_args.kwargs["pkey"] == "parsed-key"

    @pytest.mark.parametrize("marker,output", [("started", "running"), ("exit-code", "exited")])
    def test_repeated_bootstrap_does_not_rewrite_or_launch(self, tmp_path, marker, output):
        # Exercise the real shell branching, which mocks cannot validate.
        directory = tmp_path / "bootstrap"
        directory.mkdir()
        if marker == "started":
            (directory / marker).mkdir()
        else:
            (directory / marker).write_text("7\n")
        with patch(f"{COMPUTE_MODULE}.BOOTSTRAP_DIR", str(directory)):
            command = _get_bootstrap_command("exit 99")

        result = subprocess.run(shlex.split(command), capture_output=True, check=True)

        assert result.stdout.decode() == output
        assert not (directory / "runner.sh").exists()
        assert not (directory / "monitor.sh").exists()

    def test_restores_image_environment_and_physical_working_directory(self, tmp_path):
        # Black-box check of the NUL-delimited xargs/env boundary; interpreting this
        # data as shell syntax would execute substitutions or split newline values.
        environment = {
            "VALUE": "spaces and 'quotes'\n$(touch unwanted) `touch unwanted2`",
            "EMPTY": "",
        }
        env_path = tmp_path / "environ"
        env_path.write_bytes(
            b"\0".join(f"{key}={value}".encode() for key, value in environment.items()) + b"\0"
        )
        image_directory = tmp_path / "image workdir"
        image_directory.mkdir()
        cwd_link = tmp_path / "cwd"
        cwd_link.symlink_to(image_directory, target_is_directory=True)
        runner = tmp_path / "runner.sh"
        runner.write_text(
            'printf "%s\\0%s\\0%s\\0%s" "$VALUE" "$EMPTY" "${SSH_ONLY-unset}" "$PWD"\n'
        )
        command = (
            _get_image_env_and_cwd_command(str(runner))
            .replace("/proc/1/environ", shlex.quote(str(env_path)))
            .replace("/proc/1/cwd", shlex.quote(str(cwd_link)))
        )

        result = subprocess.run(
            ["/bin/sh", "-c", command],
            capture_output=True,
            check=True,
            cwd=tmp_path,
            env={"SSH_ONLY": "must not leak"},
        )

        assert result.stdout == (
            environment["VALUE"].encode()
            + b"\0\0unset\0"
            + str(image_directory.resolve()).encode()
        )
        assert not (tmp_path / "unwanted").exists()
        assert not (tmp_path / "unwanted2").exists()
        assert not (image_directory / "unwanted").exists()
        assert not (image_directory / "unwanted2").exists()

    def test_missing_image_working_directory_does_not_start_runner(self, tmp_path):
        env_path = tmp_path / "environ"
        env_path.write_bytes(b"VALUE=example\0")
        runner = tmp_path / "runner.sh"
        runner.write_text("printf started\n")
        command = (
            _get_image_env_and_cwd_command(str(runner))
            .replace("/proc/1/environ", shlex.quote(str(env_path)))
            .replace("/proc/1/cwd", shlex.quote(str(tmp_path / "missing")))
        )

        result = subprocess.run(["/bin/sh", "-c", command], capture_output=True)

        assert result.returncode != 0
        assert result.stdout == b""

    def test_oversized_environment_fails_without_starting_partial_runner(self, tmp_path):
        env_path = tmp_path / "environ"
        env_path.write_bytes(b"\0".join(f"VAR_{n}=value".encode() for n in range(100)) + b"\0")
        runner = tmp_path / "runner.sh"
        runner.write_text("printf started\n")
        command = (
            _get_image_env_and_cwd_command(str(runner))
            .replace("/proc/1/environ", shlex.quote(str(env_path)))
            .replace("/proc/1/cwd", shlex.quote(str(tmp_path)))
        )
        # Force a small limit to test the same xargs failure on Linux and macOS.
        command = command.replace("xargs -0", "xargs -s 512 -0")

        result = subprocess.run(["/bin/sh", "-c", command], capture_output=True)

        assert result.returncode != 0
        assert result.stdout == b""
