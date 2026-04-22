import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

if sys.version_info < (3, 10):
    pytest.skip("Verda requires Python 3.10", allow_module_level=True)

from verda.exceptions import APIException

from dstack._internal.core.backends.verda.compute import (
    VerdaCompute,
    VerdaInstanceBackendData,
    _create_ssh_key,
    _create_startup_script,
)
from dstack._internal.core.errors import BackendError, NoCapacityError


def _assert_terminate_call(action_mock: MagicMock):
    action_mock.assert_called_once()
    kwargs = action_mock.call_args.kwargs
    assert kwargs["id_list"] == ["instance-id"]
    assert kwargs["action"] == "delete"
    if "delete_permanently" in kwargs:
        assert kwargs["delete_permanently"] is True


class TestCreateSSHKey:
    def test_creates_ssh_key(self):
        client = MagicMock()
        client.ssh_keys.create.return_value = SimpleNamespace(id="new-ssh-key-id")

        key_id = _create_ssh_key(
            client=client,
            name="dstack-test-key",
            public_key="ssh-rsa test",
        )

        assert key_id == "new-ssh-key-id"
        client.ssh_keys.create.assert_called_once_with("dstack-test-key", "ssh-rsa test")

    def test_raises_backend_error_on_api_exception(self):
        client = MagicMock()
        client.ssh_keys.create.side_effect = APIException("invalid_request", "Boom")

        with pytest.raises(BackendError, match="creating SSH key: Boom"):
            _create_ssh_key(
                client=client,
                name="dstack-test-key",
                public_key="ssh-rsa test",
            )


class TestCreateStartupScript:
    def test_creates_startup_script(self):
        client = MagicMock()
        client.startup_scripts.create.return_value = SimpleNamespace(id="new-script-id")

        script_id = _create_startup_script(
            client=client,
            name="dstack-test-script.sh",
            script="echo bye",
        )

        assert script_id == "new-script-id"
        client.startup_scripts.create.assert_called_once_with(
            "dstack-test-script.sh",
            "echo bye",
        )

    def test_raises_backend_error_on_api_exception(self):
        client = MagicMock()
        client.startup_scripts.create.side_effect = APIException("invalid_request", "Boom")

        with pytest.raises(BackendError, match="creating startup script: Boom"):
            _create_startup_script(
                client=client,
                name="dstack-test-script.sh",
                script="echo bye",
            )


class TestCreateInstance:
    def test_cleans_up_created_ssh_keys_if_later_ssh_key_create_fails(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()

        instance_offer = SimpleNamespace(
            backend="verda",
            instance=SimpleNamespace(
                name="CPU.4V.16G",
                resources=SimpleNamespace(
                    disk=SimpleNamespace(size_mib=102400),
                    gpus=[],
                    spot=False,
                ),
            ),
            region="FIN-01",
            price=0.0279,
        )
        instance_config = SimpleNamespace(
            instance_name="verda-one-node-0",
            get_public_keys=lambda: ["ssh-rsa test-1", "ssh-rsa test-2"],
        )

        with (
            patch(
                "dstack._internal.core.backends.verda.compute.generate_unique_instance_name",
                return_value="verda-one-node-0",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_ssh_key",
                side_effect=["ssh-key-id-1", BackendError("ssh create failed")],
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_startup_script"
            ) as create_startup_script,
            patch(
                "dstack._internal.core.backends.verda.compute._delete_startup_script"
            ) as delete_startup_script,
            patch(
                "dstack._internal.core.backends.verda.compute._delete_ssh_keys"
            ) as delete_ssh_keys,
        ):
            with pytest.raises(BackendError, match="ssh create failed"):
                compute.create_instance(instance_offer, instance_config, None)

        create_startup_script.assert_not_called()
        delete_startup_script.assert_called_once_with(compute.client, None)
        delete_ssh_keys.assert_called_once_with(compute.client, ["ssh-key-id-1"])

    def test_cleans_up_ssh_keys_if_startup_script_create_fails(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()

        instance_offer = SimpleNamespace(
            backend="verda",
            instance=SimpleNamespace(
                name="CPU.4V.16G",
                resources=SimpleNamespace(
                    disk=SimpleNamespace(size_mib=102400),
                    gpus=[],
                    spot=False,
                ),
            ),
            region="FIN-01",
            price=0.0279,
        )
        instance_config = SimpleNamespace(
            instance_name="verda-one-node-0",
            get_public_keys=lambda: ["ssh-rsa test-1", "ssh-rsa test-2"],
        )

        with (
            patch(
                "dstack._internal.core.backends.verda.compute.generate_unique_instance_name",
                return_value="verda-one-node-0",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_ssh_key",
                side_effect=["ssh-key-id-1", "ssh-key-id-2"],
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_startup_script",
                side_effect=BackendError("script create failed"),
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._delete_startup_script"
            ) as delete_startup_script,
            patch(
                "dstack._internal.core.backends.verda.compute._delete_ssh_keys"
            ) as delete_ssh_keys,
        ):
            with pytest.raises(BackendError, match="script create failed"):
                compute.create_instance(instance_offer, instance_config, None)

        delete_startup_script.assert_called_once_with(compute.client, None)
        delete_ssh_keys.assert_called_once_with(compute.client, ["ssh-key-id-1", "ssh-key-id-2"])

    def test_cleans_up_startup_script_if_deploy_fails(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()

        instance_offer = SimpleNamespace(
            backend="verda",
            instance=SimpleNamespace(
                name="CPU.4V.16G",
                resources=SimpleNamespace(
                    disk=SimpleNamespace(size_mib=102400),
                    gpus=[],
                    spot=False,
                ),
            ),
            region="FIN-01",
            price=0.0279,
        )
        instance_config = SimpleNamespace(
            instance_name="verda-one-node-0",
            get_public_keys=lambda: ["ssh-rsa test"],
        )

        with (
            patch(
                "dstack._internal.core.backends.verda.compute.generate_unique_instance_name",
                return_value="verda-one-node-0",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute.get_shim_commands",
                return_value=["echo ready"],
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_ssh_key",
                return_value="ssh-key-id",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_startup_script",
                return_value="startup-script-id",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._deploy_instance",
                side_effect=NoCapacityError("no capacity"),
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._delete_startup_script"
            ) as delete_startup_script,
            patch(
                "dstack._internal.core.backends.verda.compute._delete_ssh_keys"
            ) as delete_ssh_keys,
        ):
            with pytest.raises(NoCapacityError):
                compute.create_instance(instance_offer, instance_config, None)

        delete_startup_script.assert_called_once_with(compute.client, "startup-script-id")
        delete_ssh_keys.assert_called_once_with(compute.client, ["ssh-key-id"])

    def test_stores_ssh_key_ids_in_backend_data(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()

        instance_offer = SimpleNamespace(
            backend="verda",
            instance=SimpleNamespace(
                name="CPU.4V.16G",
                resources=SimpleNamespace(
                    disk=SimpleNamespace(size_mib=102400),
                    gpus=[],
                    spot=False,
                ),
            ),
            region="FIN-01",
            price=0.0279,
        )
        instance_config = SimpleNamespace(
            instance_name="verda-one-node-0",
            get_public_keys=lambda: ["ssh-rsa test-1", "ssh-rsa test-2"],
        )
        provider_instance = SimpleNamespace(id="provider-instance-id", location="FIN-01")

        with (
            patch(
                "dstack._internal.core.backends.verda.compute.generate_unique_instance_name",
                return_value="verda-one-node-0",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute.get_shim_commands",
                return_value=["echo ready"],
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_ssh_key",
                side_effect=["ssh-key-id-1", "ssh-key-id-2"],
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._create_startup_script",
                return_value="startup-script-id",
            ),
            patch(
                "dstack._internal.core.backends.verda.compute._deploy_instance",
                return_value=provider_instance,
            ),
            patch(
                "dstack._internal.core.backends.verda.compute.JobProvisioningData",
                side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
            ),
        ):
            jpd = compute.create_instance(instance_offer, instance_config, None)

        backend_data = VerdaInstanceBackendData.load(jpd.backend_data)
        assert backend_data.startup_script_id == "startup-script-id"
        assert backend_data.ssh_key_ids == ["ssh-key-id-1", "ssh-key-id-2"]


class TestTerminateInstance:
    def test_terminate_instance_without_backend_data(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()

        compute.terminate_instance("instance-id", "FIN-01", None)

        _assert_terminate_call(compute.client.instances.action)
        compute.client.startup_scripts.delete_by_id.assert_not_called()
        compute.client.ssh_keys.delete.assert_not_called()

    def test_terminate_instance_deletes_startup_script(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()
        backend_data = VerdaInstanceBackendData(
            startup_script_id="script-id",
            ssh_key_ids=["ssh-key-id-1", "ssh-key-id-2"],
        ).json()

        compute.terminate_instance("instance-id", "FIN-01", backend_data)

        _assert_terminate_call(compute.client.instances.action)
        compute.client.startup_scripts.delete_by_id.assert_called_once_with("script-id")
        compute.client.ssh_keys.delete.assert_called_once_with(["ssh-key-id-1", "ssh-key-id-2"])

    def test_terminate_instance_still_deletes_script_when_instance_is_missing(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()
        compute.client.instances.action.side_effect = APIException("", "Invalid instance id")
        backend_data = VerdaInstanceBackendData(
            startup_script_id="script-id",
            ssh_key_ids=["ssh-key-id-1"],
        ).json()

        compute.terminate_instance("instance-id", "FIN-01", backend_data)

        compute.client.startup_scripts.delete_by_id.assert_called_once_with("script-id")
        compute.client.ssh_keys.delete.assert_called_once_with(["ssh-key-id-1"])

    def test_terminate_instance_retries_on_script_delete_error(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()
        compute.client.startup_scripts.delete_by_id.side_effect = APIException(
            "", "Random API error"
        )
        backend_data = VerdaInstanceBackendData(
            startup_script_id="script-id",
            ssh_key_ids=["ssh-key-id-1"],
        ).json()

        with pytest.raises(APIException):
            compute.terminate_instance("instance-id", "FIN-01", backend_data)

        compute.client.ssh_keys.delete.assert_not_called()

    def test_terminate_instance_retries_on_ssh_key_delete_error(self):
        compute = VerdaCompute.__new__(VerdaCompute)
        compute.client = MagicMock()
        compute.client.ssh_keys.delete.side_effect = APIException("", "Random API error")
        backend_data = VerdaInstanceBackendData(
            startup_script_id="script-id",
            ssh_key_ids=["ssh-key-id-1"],
        ).json()

        with pytest.raises(APIException):
            compute.terminate_instance("instance-id", "FIN-01", backend_data)
