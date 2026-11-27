from datetime import datetime, timezone

import pytest
import requests

from dstack._internal.core.backends.massedcompute.api_client import API_URL
from dstack._internal.core.backends.massedcompute.compute import MassedComputeCompute
from dstack._internal.core.backends.massedcompute.models import (
    MassedComputeConfig,
    MassedComputeCreds,
)
from dstack._internal.core.errors import (
    ComputeError,
    NotYetTerminated,
    ProvisioningError,
    VolumeDeletionPending,
    VolumeProvisioningError,
    VolumeProvisioningPending,
)
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.backends.orphans import OwnerType
from dstack._internal.core.models.volumes import (
    MassedComputeVolumeConfiguration,
    VolumeStatus,
)
from dstack._internal.server.testing.common import (
    get_instance_configuration,
    get_instance_offer_with_availability,
    get_job_provisioning_data,
    get_volume,
)
from dstack._internal.utils.hash import slugify

VM_ID = "465e97cc-77cc-47dd-bb7c-1835ee127f9f"
VOLUME_ID = "78ee0ea9-4c18-4aa4-b0df-aa1212734d45"
OTHER_ID = "1a821471-d1d7-4c27-971d-10d3951ccce7"
PROVIDER_REF = "abcdefgh1234"


@pytest.fixture
def compute():
    return MassedComputeCompute(MassedComputeConfig(creds=MassedComputeCreds(api_key="test")))


@pytest.fixture
def offer():
    return get_instance_offer_with_availability(backend=BackendType.MASSEDCOMPUTE)


@pytest.fixture
def storage():
    return {
        "id": VOLUME_ID,
        "name": "checkpoints",
        "status": "active",
        "canManage": True,
        "mountPath": "/persistent/checkpoints",
        "hiddenAttachedCount": 0,
        "attachedTo": [],
    }


@pytest.fixture
def managed_volume(storage):
    volume = get_volume(
        configuration=MassedComputeVolumeConfiguration(), status=VolumeStatus.SUBMITTED
    )
    storage["name"] = slugify("dstack", str(volume.id), hash_size=15)
    storage["mountPath"] = "/persistent/" + storage["name"]
    return volume


@pytest.fixture
def volume_config(compute, requests_mock, storage):
    requests_mock.get(f"{API_URL}/storage-volumes", json={"storageVolumes": [storage]})
    volume = get_volume(
        configuration=MassedComputeVolumeConfiguration(volume_id=VOLUME_ID.upper())
    )
    volume.provisioning_data = compute.register_volume(volume)
    config = get_instance_configuration()
    config.provider_ref = PROVIDER_REF
    config.volumes = [volume]
    return config


@pytest.fixture
def launch_volume_vm(compute, requests_mock, offer, volume_config, storage):
    def launch(lost_reply=False):
        response = {"exc": requests.ReadTimeout} if lost_reply else {"json": {"response": VM_ID}}
        post = requests_mock.post(f"{API_URL}/instance/launch", **response)
        data = compute.create_instance(offer, volume_config, None)
        vm = {
            "uuid": VM_ID,
            "name": post.last_request.json()["instanceName"],
            "status": "Running",
            "os_booted": True,
            "username": "Ubuntu",
            "ip": "192.0.2.1",
        }
        assert post.last_request.json()["volumeIds"] == [VOLUME_ID]
        assert data.volume_mounts == {volume_config.volumes[0].id: storage["mountPath"]}
        requests_mock.get(f"{API_URL}/instance/{VM_ID}", json={"runningInstances": [vm]})
        return data, vm

    return launch


class TestCreateInstance:
    def test_omits_volume_ids_for_a_plain_vm(self, compute, requests_mock, offer):
        post = requests_mock.post(f"{API_URL}/instance/launch", json={"response": VM_ID})
        data = compute.create_instance(offer, get_instance_configuration(), None)
        assert "volumeIds" not in post.last_request.json()
        assert data.instance_id == VM_ID
        assert data.backend_data is None and data.volume_mounts is None

    def test_fails_before_launch_if_volume_in_use(
        self, compute, requests_mock, offer, volume_config, storage
    ):
        storage["hiddenAttachedCount"] = 1
        requests_mock.get(f"{API_URL}/storage-volumes", json={"storageVolumes": [storage]})
        with pytest.raises(ComputeError, match="unavailable or in use"):
            compute.create_instance(offer, volume_config, None)
        assert all(request.method == "GET" for request in requests_mock.request_history)


class TestUpdateProvisioningData:
    def test_recovers_the_same_launch_after_a_lost_reply(
        self, compute, requests_mock, launch_volume_vm, storage
    ):
        data, vm = launch_volume_vm(lost_reply=True)
        assert data.instance_id == vm["name"]
        # Resume from the provisioning data saved by the previous worker.
        data = type(data).model_validate_json(data.model_dump_json())
        requests_mock.get(
            f"{API_URL}/instance",
            [
                {"json": {"runningInstances": [{**vm, "name": vm["name"] + "-other"}]}},
                {"json": {"runningInstances": [vm, {**vm, "uuid": OTHER_ID}]}},
                {"json": {"runningInstances": [vm]}},
            ],
        )
        compute.update_provisioning_data(data, "", "")
        assert data.instance_id == vm["name"] and data.hostname is None
        with pytest.raises(ComputeError, match="Multiple"):
            compute.update_provisioning_data(data, "", "")
        compute.update_provisioning_data(data, "", "")
        assert data.instance_id == VM_ID and data.hostname is None
        storage["attachedTo"] = [{"uuid": VM_ID.upper()}]
        requests_mock.get(f"{API_URL}/storage-volumes", json={"storageVolumes": [storage]})
        compute.update_provisioning_data(data, "", "")
        assert data.hostname == vm["ip"] and data.backend_data is None
        assert [r.method for r in requests_mock.request_history].count("POST") == 1

    @pytest.mark.parametrize(
        "changes",
        [
            {"attachedTo": []},
            {"attachedTo": [{"uuid": OTHER_ID}]},
            {"hiddenAttachedCount": 1},
            {"mountPath": "/persistent/unexpected"},
        ],
    )
    def test_rejects_changed_mount_or_owner(
        self, compute, requests_mock, launch_volume_vm, storage, changes
    ):
        data, _ = launch_volume_vm()
        storage["attachedTo"] = [{"uuid": VM_ID}]
        storage.update(changes)
        requests_mock.get(f"{API_URL}/storage-volumes", json={"storageVolumes": [storage]})
        with pytest.raises(ProvisioningError, match="failed to attach"):
            compute.update_provisioning_data(data, "", "")
        assert data.hostname is None


class TestTerminateInstance:
    @pytest.mark.parametrize("lost_reply", [False, True])
    def test_terminates_by_uuid_and_accepts_disappearance(
        self, compute, requests_mock, launch_volume_vm, lost_reply
    ):
        data, vm = launch_volume_vm(lost_reply=lost_reply)
        vm["status"] = "Stopped"
        snapshots = [{"json": {"runningInstances": [vm]}}, {"json": {"runningInstances": []}}]
        if lost_reply:
            requests_mock.get(f"{API_URL}/instance", snapshots)
        requests_mock.get(f"{API_URL}/instance/{VM_ID}", snapshots)
        terminate = requests_mock.post(f"{API_URL}/instance/terminate", status_code=202)
        # A stopped VM on MassedCompute is still billable.
        with pytest.raises(NotYetTerminated):
            compute.terminate_instance(data.instance_id, "any", data.backend_data)
        compute.terminate_instance(data.instance_id, "any", data.backend_data)
        assert terminate.call_count == 1
        assert terminate.last_request.json() == {"instanceUuids": [VM_ID]}


class TestListResourceGroups:
    def test_reports_volume_vms_for_manual_cleanup(self, compute, requests_mock, launch_volume_vm):
        _, vm = launch_volume_vm()
        plain = {
            **vm,
            "uuid": OTHER_ID,
            "name": "dstack-main-gpu-abcdefgh12345678",
            "created": "2026-11-25T14:48:48.000Z",
        }
        requests_mock.get(
            f"{API_URL}/instance", json={"runningInstances": [plain, vm, {**vm, "name": "manual"}]}
        )
        ordinary, mounted = compute.list_resource_groups().resource_groups
        assert ordinary.owner_type == OwnerType.INSTANCE
        assert ordinary.primary_id == OTHER_ID and ordinary.backend_data is None
        assert ordinary.created_at == datetime(2026, 11, 25, 14, 48, 48, tzinfo=timezone.utc)
        assert ordinary.provider_ref == mounted.provider_ref == PROVIDER_REF
        assert mounted.primary_id == VM_ID
        with pytest.raises(ComputeError, match="cannot flush"):
            compute.delete_resource_group(mounted)


class TestCreateVolume:
    def test_conflicting_first_create_never_adopts_existing_storage(
        self, compute, requests_mock, storage, managed_volume
    ):
        lookup = requests_mock.get(
            f"{API_URL}/storage-volumes", json={"storageVolumes": [storage]}
        )
        requests_mock.post(f"{API_URL}/storage-volumes", status_code=409)
        with pytest.raises(VolumeProvisioningError, match="409") as rejected:
            compute.create_volume(managed_volume)
        assert rejected.value.volume_id is None and not lookup.called

    @pytest.mark.parametrize("lost_reply", [False, True])
    def test_sends_one_create_then_recovers_by_name_or_uuid(
        self, compute, requests_mock, storage, managed_volume, lost_reply
    ):
        reply = (
            {"exc": requests.ReadTimeout} if lost_reply else {"json": {"storageVolume": storage}}
        )
        post = requests_mock.post(f"{API_URL}/storage-volumes", **reply)
        with pytest.raises(VolumeProvisioningPending) as result:
            compute.create_volume(managed_volume)
        assert result.value.volume_id == (None if lost_reply else VOLUME_ID)
        assert post.last_request.json() == {"name": storage["name"]}

        managed_volume.status = VolumeStatus.PROVISIONING
        managed_volume.volume_id = result.value.volume_id
        requests_mock.get(
            f"{API_URL}/storage-volumes",
            [
                {"json": {"storageVolumes": []}},
                {"json": {"storageVolumes": [{**storage, "status": "creating"}]}},
                {"json": {"storageVolumes": [storage]}},
            ],
        )
        # Empty snapshots are lookup-only even after a worker lost its reply.
        with pytest.raises(VolumeProvisioningPending):
            compute.create_volume(managed_volume)
        with pytest.raises(VolumeProvisioningPending) as found:
            compute.create_volume(managed_volume)
        assert found.value.volume_id == VOLUME_ID
        managed_volume.volume_id = found.value.volume_id
        data = compute.create_volume(managed_volume)
        assert data.mount_on_instance and data.volume_id == VOLUME_ID
        assert post.call_count == 1

    def test_preserves_id_of_unusable_managed_volume(
        self, compute, requests_mock, storage, managed_volume
    ):
        managed_volume.status = VolumeStatus.PROVISIONING
        storage["mountPath"] = "/"
        requests_mock.get(f"{API_URL}/storage-volumes", json={"storageVolumes": [storage]})
        with pytest.raises(VolumeProvisioningError) as result:
            compute.create_volume(managed_volume)
        assert result.value.volume_id == VOLUME_ID


class TestDeleteVolume:
    def test_persists_recovered_uuid_before_deleting(
        self, compute, requests_mock, storage, managed_volume
    ):
        requests_mock.get(
            f"{API_URL}/storage-volumes",
            [
                {"json": {"storageVolumes": []}},
                {"json": {"storageVolumes": [storage]}},
            ],
        )
        delete = requests_mock.delete(f"{API_URL}/storage-volumes/{VOLUME_ID}", status_code=404)
        with pytest.raises(VolumeDeletionPending):
            compute.delete_volume(managed_volume)
        with pytest.raises(VolumeDeletionPending) as found:
            compute.delete_volume(managed_volume)
        assert found.value.volume_id == VOLUME_ID
        assert not delete.called
        managed_volume.volume_id = found.value.volume_id
        compute.delete_volume(managed_volume)
        assert delete.call_count == 1

    def test_preserves_external_storage(self, compute, requests_mock):
        volume = get_volume(
            configuration=MassedComputeVolumeConfiguration(volume_id=VOLUME_ID), external=True
        )
        compute.delete_volume(volume)
        assert not requests_mock.called


class TestGetVolumeMountsToSync:
    @pytest.mark.parametrize("status", [None, "Stopped", "Deleting", "Running"])
    def test_decides_from_confirmed_vm_snapshot(
        self, compute, requests_mock, volume_config, status
    ):
        data = get_job_provisioning_data(backend=BackendType.MASSEDCOMPUTE)
        data.instance_id = VM_ID
        data.volume_mounts = {volume_config.volumes[0].id: "/persistent/checkpoints"}
        vm = {"uuid": VM_ID, "name": "vm", "status": status}
        requests_mock.get(
            f"{API_URL}/instance/{VM_ID}", json={"runningInstances": [vm] if status else []}
        )
        if status == "Stopped":
            with pytest.raises(ComputeError, match="Restart"):
                compute.get_volume_mounts_to_sync(data)
        elif status == "Deleting":
            with pytest.raises(NotYetTerminated):
                compute.get_volume_mounts_to_sync(data)
        else:
            assert compute.get_volume_mounts_to_sync(data) == (
                ["/persistent/checkpoints"] if status else None
            )
