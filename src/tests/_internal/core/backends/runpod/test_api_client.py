from dstack._internal.core.backends.runpod.api_client import (
    RunpodApiClient,
    _generate_cpu_pod_deployment_mutation,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_generate_cpu_pod_deployment_mutation():
    mutation = _generate_cpu_pod_deployment_mutation(
        name="cpu-test",
        image_name="python:3.11-slim",
        instance_id="cpu3g-2-8",
        cloud_type="SECURE",
        deploy_cost=0.08,
        start_ssh=True,
        data_center_id="AP-JP-1",
        container_disk_in_gb=5,
        docker_args='{"cmd":["echo hi"]}',
        ports="22/tcp, 8080/http",
        volume_mount_path="/workspace",
        env={"HELLO": "WORLD"},
        template_id="runpod-ubuntu",
        network_volume_id="vol-1",
        container_registry_auth_id="cred-1",
    )

    assert "deployCpuPod" in mutation
    assert 'name: "cpu-test"' in mutation
    assert 'imageName: "python:3.11-slim"' in mutation
    assert 'instanceId: "cpu3g-2-8"' in mutation
    assert "cloudType: SECURE" in mutation
    assert "deployCost: 0.08" in mutation
    assert "startSsh: true" in mutation
    assert 'dataCenterId: "AP-JP-1"' in mutation
    assert "containerDiskInGb: 5" in mutation
    assert 'ports: "22/tcp,8080/http"' in mutation
    assert 'volumeMountPath: "/workspace"' in mutation
    assert 'env: [{ key: "HELLO", value: "WORLD" }]' in mutation
    assert 'templateId: "runpod-ubuntu"' in mutation
    assert 'networkVolumeId: "vol-1"' in mutation
    assert 'containerRegistryAuthId: "cred-1"' in mutation


def test_create_cpu_pod_uses_deploy_cpu_pod(monkeypatch):
    client = RunpodApiClient(api_key="test")
    query = {}

    def fake_make_request(data):
        query["value"] = data["query"]
        return _Response({"data": {"deployCpuPod": {"id": "cpu-pod-1"}}})

    monkeypatch.setattr(client, "_make_request", fake_make_request)

    response = client.create_cpu_pod(
        name="cpu-test",
        image_name="python:3.11-slim",
        instance_id="cpu3g-2-8",
        cloud_type="SECURE",
        deploy_cost=0.08,
    )

    assert response["id"] == "cpu-pod-1"
    assert "deployCpuPod" in query["value"]
    assert "podFindAndDeployOnDemand" not in query["value"]
