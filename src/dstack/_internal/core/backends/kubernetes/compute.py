import shlex
import subprocess
import tempfile
import time
from enum import Enum
from typing import List, Optional

from gpuhunt import AcceleratorVendor
from kubernetes import client
from typing_extensions import Self

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithFilteredOffersCached,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    ComputeWithPrivilegedSupport,
    generate_unique_gateway_instance_name,
    generate_unique_instance_name_for_job,
    get_docker_commands,
    get_dstack_gateway_commands,
)
from dstack._internal.core.backends.kubernetes.models import (
    KubernetesConfig,
    KubernetesProxyJumpConfig,
)
from dstack._internal.core.backends.kubernetes.resources import (
    AMD_GPU_DEVICE_ID_LABEL_PREFIX,
    AMD_GPU_NAME_TO_DEVICE_IDS,
    AMD_GPU_NODE_TAINT,
    AMD_GPU_RESOURCE,
    DUMMY_REGION,
    NVIDIA_GPU_NAME_TO_GPU_INFO,
    NVIDIA_GPU_NODE_TAINT,
    NVIDIA_GPU_PRODUCT_LABEL,
    NVIDIA_GPU_RESOURCE,
    PodPhase,
    TaintEffect,
    format_memory,
    get_amd_gpu_from_node_labels,
    get_gpu_request_from_gpu_spec,
    get_instance_offer_from_node,
    get_instance_offers,
    get_node_labels,
    get_node_name,
    get_nvidia_gpu_from_node_labels,
    is_hard_taint,
    is_taint_tolerated,
)
from dstack._internal.core.backends.kubernetes.utils import (
    call_api_method,
    get_api_from_config_data,
)
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError, ProvisioningError
from dstack._internal.core.models.common import CoreModel
from dstack._internal.core.models.gateways import (
    GatewayComputeConfiguration,
    GatewayProvisioningData,
)
from dstack._internal.core.models.instances import (
    Gpu,
    InstanceOfferWithAvailability,
    SSHConnectionParams,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.resources import CPUSpec, GPUSpec
from dstack._internal.core.models.routers import AnyRouterConfig
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.common import get_or_error
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

JUMP_POD_IMAGE = "testcontainers/sshd:1.3.0@sha256:c50c0f59554dcdb2d9e5e705112144428ae9d04ac0af6322b365a18e24213a6a"
JUMP_POD_SSH_PORT = 22
JUMP_POD_USER = "root"


class Operator(str, Enum):
    EXISTS = "Exists"
    IN = "In"


class KubernetesBackendData(CoreModel):
    jump_pod_name: str
    jump_pod_service_name: str
    user_ssh_public_key: str

    @classmethod
    def load(cls, raw: str) -> Self:
        return cls.__response__.parse_raw(raw)


class KubernetesCompute(
    ComputeWithFilteredOffersCached,
    ComputeWithPrivilegedSupport,
    ComputeWithGatewaySupport,
    ComputeWithMultinodeSupport,
    Compute,
):
    def __init__(self, config: KubernetesConfig):
        super().__init__()
        self.config = config.copy()
        proxy_jump = self.config.proxy_jump
        if proxy_jump is None:
            proxy_jump = KubernetesProxyJumpConfig()
        self.proxy_jump = proxy_jump
        self.api = get_api_from_config_data(config.kubeconfig.data)

    def get_offers_by_requirements(
        self, requirements: Requirements
    ) -> list[InstanceOfferWithAvailability]:
        return get_instance_offers(self.api, requirements)

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: list[Volume],
        placement_group: Optional[PlacementGroup],
    ) -> JobProvisioningData:
        instance_name = generate_unique_instance_name_for_job(run, job)
        assert run.run_spec.ssh_key_pub is not None
        commands = get_docker_commands(
            [run.run_spec.ssh_key_pub.strip(), project_ssh_public_key.strip()]
        )
        # There is a one jump pod per Kubernetes backend that is used
        # as an ssh proxy jump to connect to all other services in Kubernetes.
        # The service is created here and configured later in update_provisioning_data()
        jump_pod_name = f"dstack-{run.project_name}-ssh-jump-pod"
        jump_pod_service_name = _get_pod_service_name(jump_pod_name)
        _create_jump_pod_service_if_not_exists(
            api=self.api,
            namespace=self.config.namespace,
            jump_pod_name=jump_pod_name,
            jump_pod_service_name=jump_pod_service_name,
            jump_pod_port=self.proxy_jump.port,
            project_ssh_public_key=project_ssh_public_key.strip(),
        )

        resources_requests: dict[str, str] = {}
        resources_limits: dict[str, str] = {}
        node_affinity: Optional[client.V1NodeAffinity] = None
        tolerations: list[client.V1Toleration] = []
        volumes_: list[client.V1Volume] = []
        volume_mounts: list[client.V1VolumeMount] = []

        resources_spec = job.job_spec.requirements.resources
        assert isinstance(resources_spec.cpu, CPUSpec)
        if (cpu_min := resources_spec.cpu.count.min) is not None:
            resources_requests["cpu"] = str(cpu_min)
        if (cpu_max := resources_spec.cpu.count.max) is not None:
            resources_limits["cpu"] = str(cpu_max)
        if (gpu_spec := resources_spec.gpu) is not None:
            if (gpu_request := get_gpu_request_from_gpu_spec(gpu_spec)) > 0:
                gpu_resource, node_affinity, node_taint = _get_pod_spec_parameters_for_gpu(
                    self.api, gpu_spec
                )
                logger.debug("Requesting GPU resource: %s=%d", gpu_resource, gpu_request)
                resources_requests[gpu_resource] = str(gpu_request)
                # Limit must be set (GPU resources cannot be overcommitted)
                # and must be equal to request.
                resources_limits[gpu_resource] = str(gpu_request)
                # It should be NoSchedule, but we also add NoExecute toleration just in case.
                for effect in [TaintEffect.NO_SCHEDULE, TaintEffect.NO_EXECUTE]:
                    tolerations.append(
                        client.V1Toleration(
                            key=node_taint, operator=Operator.EXISTS, effect=effect
                        )
                    )
        if (memory_min := resources_spec.memory.min) is not None:
            resources_requests["memory"] = format_memory(memory_min)
        if (memory_max := resources_spec.memory.max) is not None:
            resources_limits["memory"] = format_memory(memory_max)
        if (disk_spec := resources_spec.disk) is not None:
            if (disk_min := disk_spec.size.min) is not None:
                resources_requests["ephemeral-storage"] = format_memory(disk_min)
            if (disk_max := disk_spec.size.max) is not None:
                resources_limits["ephemeral-storage"] = format_memory(disk_max)
        if (shm_size := resources_spec.shm_size) is not None:
            shm_volume_name = "dev-shm"
            volumes_.append(
                client.V1Volume(
                    name=shm_volume_name,
                    empty_dir=client.V1EmptyDirVolumeSource(
                        medium="Memory",
                        size_limit=format_memory(shm_size),
                    ),
                )
            )
            volume_mounts.append(
                client.V1VolumeMount(
                    name=shm_volume_name,
                    mount_path="/dev/shm",
                )
            )

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=instance_name,
                labels={"app.kubernetes.io/name": instance_name},
            ),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name=f"{instance_name}-container",
                        image=job.job_spec.image_name,
                        command=["/bin/sh"],
                        args=["-c", " && ".join(commands)],
                        ports=[
                            client.V1ContainerPort(
                                container_port=DSTACK_RUNNER_SSH_PORT,
                            )
                        ],
                        security_context=client.V1SecurityContext(
                            run_as_user=0,
                            run_as_group=0,
                            privileged=job.job_spec.privileged,
                            capabilities=client.V1Capabilities(
                                add=[
                                    # Allow to increase hard resource limits, see getrlimit(2)
                                    "SYS_RESOURCE",
                                ],
                            ),
                        ),
                        resources=client.V1ResourceRequirements(
                            requests=resources_requests,
                            limits=resources_limits,
                        ),
                        volume_mounts=volume_mounts,
                    )
                ],
                affinity=client.V1Affinity(
                    node_affinity=node_affinity,
                ),
                tolerations=tolerations,
                volumes=volumes_,
            ),
        )
        self.api.create_namespaced_pod(
            namespace=self.config.namespace,
            body=pod,
        )
        self.api.create_namespaced_service(
            namespace=self.config.namespace,
            body=client.V1Service(
                metadata=client.V1ObjectMeta(name=_get_pod_service_name(instance_name)),
                spec=client.V1ServiceSpec(
                    type="ClusterIP",
                    selector={"app.kubernetes.io/name": instance_name},
                    ports=[client.V1ServicePort(port=DSTACK_RUNNER_SSH_PORT)],
                ),
            ),
        )

        backend_data = KubernetesBackendData(
            jump_pod_name=jump_pod_name,
            jump_pod_service_name=jump_pod_service_name,
            user_ssh_public_key=run.run_spec.ssh_key_pub.strip(),
        )
        return JobProvisioningData(
            backend=instance_offer.backend,
            instance_id=instance_name,
            region=instance_offer.region,
            price=instance_offer.price,
            username="root",
            ssh_port=DSTACK_RUNNER_SSH_PORT,
            dockerized=False,
            # Although we can already get Service's ClusterIP from the `V1Service` object returned
            # by the `create_namespaced_service` method, we still need:
            # - updated instance offer
            # - job pod's PodIP for multinode runs
            # - jump pod node's ExternalIP and jump pod service's NodePort for ssh_proxy
            # We'll update all these fields once both the jump pod and the job pod are assigned
            # to the nodes.
            hostname=None,
            instance_type=instance_offer.instance,
            internal_ip=None,
            ssh_proxy=None,
            backend_data=backend_data.json(),
        )

    def update_provisioning_data(
        self,
        provisioning_data: JobProvisioningData,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
    ):
        if provisioning_data.backend_data is not None:
            # Before running a job, ensure the jump pod is running and has user's public SSH key.
            backend_data = KubernetesBackendData.load(provisioning_data.backend_data)
            ssh_proxy = _check_and_configure_jump_pod_service(
                api=self.api,
                namespace=self.config.namespace,
                jump_pod_name=backend_data.jump_pod_name,
                jump_pod_service_name=backend_data.jump_pod_service_name,
                jump_pod_hostname=self.proxy_jump.hostname,
                project_ssh_private_key=project_ssh_private_key,
                user_ssh_public_key=backend_data.user_ssh_public_key,
            )
            if ssh_proxy is None:
                # Jump pod is not ready yet
                return
            provisioning_data.ssh_proxy = ssh_proxy
            # Remove backend data to save space in DB and skip this step
            # in case update_provisioning_data() is called again.
            provisioning_data.backend_data = None

        pod = self.api.read_namespaced_pod(
            name=provisioning_data.instance_id,
            namespace=self.config.namespace,
        )
        if pod.status is None:
            return
        pod_ip = pod.status.pod_ip
        if not pod_ip:
            return
        provisioning_data.internal_ip = pod_ip
        service = self.api.read_namespaced_service(
            name=_get_pod_service_name(provisioning_data.instance_id),
            namespace=self.config.namespace,
        )
        service_spec = get_or_error(service.spec)
        provisioning_data.hostname = get_or_error(service_spec.cluster_ip)
        pod_spec = get_or_error(pod.spec)
        node = self.api.read_node(name=get_or_error(pod_spec.node_name))
        # In the original offer, the resources have already been adjusted according to
        # the run configuration resource requirements, see get_offers_by_requirements()
        original_resources = provisioning_data.instance_type.resources
        instance_offer = get_instance_offer_from_node(
            node=node,
            cpu_request=original_resources.cpus,
            memory_mib_request=original_resources.memory_mib,
            gpu_request=len(original_resources.gpus),
            disk_mib_request=original_resources.disk.size_mib,
        )
        if instance_offer is not None:
            provisioning_data.instance_type = instance_offer.instance
            provisioning_data.region = instance_offer.region
            provisioning_data.price = instance_offer.price

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        call_api_method(
            self.api.delete_namespaced_service,
            expected=404,
            name=_get_pod_service_name(instance_id),
            namespace=self.config.namespace,
            body=client.V1DeleteOptions(),
        )
        call_api_method(
            self.api.delete_namespaced_pod,
            expected=404,
            name=instance_id,
            namespace=self.config.namespace,
            body=client.V1DeleteOptions(),
        )

    def create_gateway(
        self,
        configuration: GatewayComputeConfiguration,
    ) -> GatewayProvisioningData:
        # Gateway creation is currently limited to Kubernetes with Load Balancer support.
        # If the cluster does not support Load Balancer, the service will be provisioned but
        # the external IP/hostname will never be allocated.

        # TODO: By default EKS creates a Classic Load Balancer for Load Balancer services.
        # Consider deploying an NLB. It seems it requires some extra configuration on the cluster:
        # https://docs.aws.amazon.com/eks/latest/userguide/network-load-balancing.html
        if configuration.instance_type is not None:
            raise ComputeError(
                "The `kubernetes` backend does not support the `instance_type`"
                " gateway configuration property"
            )
        instance_name = generate_unique_gateway_instance_name(configuration)
        commands = _get_gateway_commands(
            authorized_keys=[configuration.ssh_key_pub], router=configuration.router
        )
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=instance_name,
                labels={"app.kubernetes.io/name": instance_name},
            ),
            spec=client.V1PodSpec(
                containers=[
                    client.V1Container(
                        name=f"{instance_name}-container",
                        image="ubuntu:22.04",
                        command=["/bin/sh"],
                        args=["-c", " && ".join(commands)],
                        ports=[
                            client.V1ContainerPort(
                                container_port=22,
                            ),
                            client.V1ContainerPort(
                                container_port=80,
                            ),
                            client.V1ContainerPort(
                                container_port=443,
                            ),
                        ],
                        security_context=client.V1SecurityContext(
                            run_as_user=0,
                            run_as_group=0,
                        ),
                    )
                ]
            ),
        )
        self.api.create_namespaced_pod(
            namespace=self.config.namespace,
            body=pod,
        )
        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=_get_pod_service_name(instance_name),
            ),
            spec=client.V1ServiceSpec(
                type="LoadBalancer",
                selector={"app.kubernetes.io/name": instance_name},
                ports=[
                    client.V1ServicePort(
                        name="ssh",
                        port=22,
                        target_port=22,
                    ),
                    client.V1ServicePort(
                        name="http",
                        port=80,
                        target_port=80,
                    ),
                    client.V1ServicePort(
                        name="https",
                        port=443,
                        target_port=443,
                    ),
                ],
            ),
        )
        self.api.create_namespaced_service(
            namespace=self.config.namespace,
            body=service,
        )
        # address is eiher a domain name or an IP address
        address = _wait_for_load_balancer_address(
            api=self.api,
            namespace=self.config.namespace,
            service_name=_get_pod_service_name(instance_name),
        )
        region = DUMMY_REGION
        if address is None:
            self.terminate_instance(instance_name, region=region)
            raise ComputeError(
                "Failed to get gateway hostname. "
                "Ensure the Kubernetes cluster supports Load Balancer services."
            )
        return GatewayProvisioningData(
            instance_id=instance_name,
            ip_address=address,
            region=region,
        )

    def terminate_gateway(
        self,
        instance_id: str,
        configuration: GatewayComputeConfiguration,
        backend_data: Optional[str] = None,
    ):
        self.terminate_instance(
            instance_id=instance_id,
            region=configuration.region,
            backend_data=backend_data,
        )


def _get_pod_spec_parameters_for_gpu(
    api: client.CoreV1Api, gpu_spec: GPUSpec
) -> tuple[str, client.V1NodeAffinity, str]:
    nodes = api.list_node().items
    gpu_vendor = gpu_spec.vendor
    # If no vendor specified, we assume it's NVIDIA. Technically, it's possible to request either
    # NVIDIA or AMD in the run configuration using only GPU names (e.g.,`gpu: H100,MI300X:8`),
    # but we ignore such configurations as it's hard to translate them to K8s request.
    if gpu_vendor is None or gpu_vendor == AcceleratorVendor.NVIDIA:
        node_affinity = _get_nvidia_gpu_node_affinity(gpu_spec, nodes)
        return NVIDIA_GPU_RESOURCE, node_affinity, NVIDIA_GPU_NODE_TAINT
    if gpu_vendor == AcceleratorVendor.AMD:
        node_affinity = _get_amd_gpu_node_affinity(gpu_spec, nodes)
        return AMD_GPU_RESOURCE, node_affinity, AMD_GPU_NODE_TAINT
    raise ComputeError(f"Unsupported GPU vendor: {gpu_vendor}")


def _get_nvidia_gpu_node_affinity(
    gpu_spec: GPUSpec, nodes: list[client.V1Node]
) -> client.V1NodeAffinity:
    matching_gpu_label_values: set[str] = set()
    for node in nodes:
        labels = get_node_labels(node)
        gpu = get_nvidia_gpu_from_node_labels(labels)
        if gpu is not None and _gpu_matches_gpu_spec(gpu, gpu_spec):
            matching_gpu_label_values.add(labels[NVIDIA_GPU_PRODUCT_LABEL])
    if not matching_gpu_label_values:
        raise ComputeError(
            f"NVIDIA GPU is requested but no matching GPU labels found: {gpu_spec=}"
        )
    logger.debug(
        "Selecting nodes by labels %s for NVIDIA %s", matching_gpu_label_values, gpu_spec.name
    )
    return client.V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
            node_selector_terms=[
                client.V1NodeSelectorTerm(
                    match_expressions=[
                        client.V1NodeSelectorRequirement(
                            key=NVIDIA_GPU_PRODUCT_LABEL,
                            operator=Operator.IN,
                            values=list(matching_gpu_label_values),
                        ),
                    ],
                ),
            ],
        ),
    )


def _get_amd_gpu_node_affinity(
    gpu_spec: GPUSpec, nodes: list[client.V1Node]
) -> client.V1NodeAffinity:
    matching_device_ids: set[int] = set()
    for node in nodes:
        labels = get_node_labels(node)
        gpu = get_amd_gpu_from_node_labels(labels)
        if gpu is not None and _gpu_matches_gpu_spec(gpu, gpu_spec):
            matching_device_ids.update(AMD_GPU_NAME_TO_DEVICE_IDS[gpu.name])
    return client.V1NodeAffinity(
        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
            node_selector_terms=[
                client.V1NodeSelectorTerm(
                    match_expressions=[
                        client.V1NodeSelectorRequirement(
                            key=f"{AMD_GPU_DEVICE_ID_LABEL_PREFIX}{device_id:x}",
                            operator=Operator.EXISTS,
                        ),
                    ],
                )
                for device_id in matching_device_ids
            ],
        ),
    )


def _gpu_matches_gpu_spec(gpu: Gpu, gpu_spec: GPUSpec) -> bool:
    if gpu_spec.vendor is not None and gpu.vendor != gpu_spec.vendor:
        return False
    if gpu_spec.name is not None and gpu.name.lower() not in map(str.lower, gpu_spec.name):
        return False
    if gpu_spec.memory is not None:
        min_memory_gib = gpu_spec.memory.min
        if min_memory_gib is not None and gpu.memory_mib < min_memory_gib * 1024:
            return False
        max_memory_gib = gpu_spec.memory.max
        if max_memory_gib is not None and gpu.memory_mib > max_memory_gib * 1024:
            return False
    if gpu_spec.compute_capability is not None:
        if gpu.vendor != AcceleratorVendor.NVIDIA:
            return False
        gpu_info = NVIDIA_GPU_NAME_TO_GPU_INFO.get(gpu.name)
        if gpu_info is None:
            return False
        if gpu_info.compute_capability < gpu_spec.compute_capability:
            return False
    return True


def _create_jump_pod_service_if_not_exists(
    api: client.CoreV1Api,
    namespace: str,
    jump_pod_name: str,
    jump_pod_service_name: str,
    jump_pod_port: Optional[int],
    project_ssh_public_key: str,
) -> None:
    service: Optional[client.V1Service] = None
    pod: Optional[client.V1Pod] = None
    _namespace = call_api_method(
        api.read_namespace,
        expected=404,
        name=namespace,
    )
    if _namespace is None:
        _namespace = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=namespace,
                labels={"app.kubernetes.io/name": namespace},
            ),
        )
        api.create_namespace(body=_namespace)
    else:
        service = call_api_method(
            api.read_namespaced_service,
            expected=404,
            name=jump_pod_service_name,
            namespace=namespace,
        )
        pod = call_api_method(
            api.read_namespaced_pod,
            expected=404,
            name=jump_pod_name,
            namespace=namespace,
        )

    # The service may exist without the pod if the node on which the jump pod was running
    # has been deleted.
    if service is not None and pod is not None:
        return

    call_api_method(
        api.delete_namespaced_pod,
        expected=404,
        namespace=namespace,
        name=jump_pod_name,
    )
    # False if we found at least one node without any "hard" taint, that is, if we don't need to
    # specify the toleration.
    toleration_required = True
    # (key, effect) pairs.
    tolerated_taints: set[tuple[str, str]] = set()
    for node in api.list_node().items:
        if (node_spec := node.spec) is None:
            continue
        # True if the node has at least one NoExecute or NoSchedule taint.
        has_hard_taint = False
        taints = node_spec.taints or []
        for taint in taints:
            # A "soft" taint, ignore.
            if not is_hard_taint(taint):
                continue
            has_hard_taint = True
            if is_taint_tolerated(taint):
                tolerated_taints.add((taint.key, taint.effect))
        if not has_hard_taint:
            toleration_required = False
            break
    tolerations: list[client.V1Toleration] = []
    if toleration_required:
        for key, effect in tolerated_taints:
            tolerations.append(
                client.V1Toleration(key=key, operator=Operator.EXISTS, effect=effect)
            )
        if not tolerations:
            logger.warning("No appropriate node found, the jump pod may never be scheduled")
    commands = _get_jump_pod_commands(authorized_keys=[project_ssh_public_key])
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=jump_pod_name,
            labels={"app.kubernetes.io/name": jump_pod_name},
        ),
        spec=client.V1PodSpec(
            containers=[
                client.V1Container(
                    name=f"{jump_pod_name}-container",
                    image=JUMP_POD_IMAGE,
                    command=["/bin/sh"],
                    args=["-c", " && ".join(commands)],
                    ports=[
                        client.V1ContainerPort(
                            container_port=JUMP_POD_SSH_PORT,
                        )
                    ],
                )
            ],
            tolerations=tolerations,
        ),
    )
    api.create_namespaced_pod(
        namespace=namespace,
        body=pod,
    )
    call_api_method(
        api.delete_namespaced_service,
        expected=404,
        namespace=namespace,
        name=jump_pod_service_name,
    )
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name=jump_pod_service_name),
        spec=client.V1ServiceSpec(
            type="NodePort",
            selector={"app.kubernetes.io/name": jump_pod_name},
            ports=[
                client.V1ServicePort(
                    port=JUMP_POD_SSH_PORT,
                    target_port=JUMP_POD_SSH_PORT,
                    node_port=jump_pod_port,
                )
            ],
        ),
    )
    api.create_namespaced_service(
        namespace=namespace,
        body=service,
    )


def _check_and_configure_jump_pod_service(
    api: client.CoreV1Api,
    namespace: str,
    jump_pod_name: str,
    jump_pod_service_name: str,
    jump_pod_hostname: Optional[str],
    project_ssh_private_key: str,
    user_ssh_public_key: str,
) -> Optional[SSHConnectionParams]:
    jump_pod = api.read_namespaced_pod(
        namespace=namespace,
        name=jump_pod_name,
    )
    jump_pod_phase = PodPhase(get_or_error(get_or_error(jump_pod.status).phase))
    if jump_pod_phase.is_finished():
        raise ProvisioningError(f"Jump pod {jump_pod_name} is unexpectedly finished")
    if not jump_pod_phase.is_running():
        logger.debug("Jump pod %s is not running yet", jump_pod_name)
        return None

    if jump_pod_hostname is None:
        jump_pod_node_name = get_or_error(get_or_error(jump_pod.spec).node_name)
        cluster_external_ips: list[str] = []
        for node in api.list_node().items:
            node_external_ips = [
                node_address.address
                for node_address in get_or_error(get_or_error(node.status).addresses)
                if node_address.type == "ExternalIP"
            ]
            if node_external_ips:
                if get_node_name(node) == jump_pod_node_name:
                    jump_pod_hostname = node_external_ips[0]
                    break
                cluster_external_ips.extend(node_external_ips)
        if jump_pod_hostname is None:
            if not cluster_external_ips:
                raise ProvisioningError(
                    "Failed to acquire an IP for jump pod automatically."
                    " Specify proxy_jump.hostname for Kubernetes backend."
                )
            jump_pod_hostname = cluster_external_ips[0]
            logger.info(
                (
                    "Jump pod %s is running on node %s which has no external IP,"
                    " picking a random external IP: %s"
                ),
                jump_pod_name,
                jump_pod_node_name,
                jump_pod_hostname,
            )

    jump_pod_service = api.read_namespaced_service(
        name=jump_pod_service_name,
        namespace=namespace,
    )
    jump_pod_service_ports = get_or_error(jump_pod_service.spec).ports
    if not jump_pod_service_ports:
        raise ProvisioningError("Jump pod service %s ports are empty", jump_pod_service_name)
    if (jump_pod_port := jump_pod_service_ports[0].node_port) is None:
        raise ProvisioningError("Jump pod service %s port is not set", jump_pod_service_name)

    ssh_exit_status, ssh_output = _run_ssh_command(
        hostname=jump_pod_hostname,
        port=jump_pod_port,
        username=JUMP_POD_USER,
        ssh_private_key=project_ssh_private_key,
        # command= in authorized_keys is equivalent to ForceCommand in sshd_config
        # By forcing the /bin/false command we only allow proxy jumping, no shell access
        command=f"""
            if grep -qvF '{user_ssh_public_key}' ~/.ssh/authorized_keys; then
                echo 'command="/bin/false" {user_ssh_public_key}' >> ~/.ssh/authorized_keys
            fi
        """,
    )
    if ssh_exit_status != 0:
        logger.debug(
            "Jump pod %s @ %s:%d, SSH command failed, exit status: %d, output: %s",
            jump_pod_name,
            jump_pod_hostname,
            jump_pod_port,
            ssh_exit_status,
            ssh_output,
        )
        return None

    logger.debug(
        "Jump pod %s is available @ %s:%d",
        jump_pod_name,
        jump_pod_hostname,
        jump_pod_port,
    )
    return SSHConnectionParams(
        hostname=jump_pod_hostname,
        port=jump_pod_port,
        username=JUMP_POD_USER,
    )


def _get_jump_pod_commands(authorized_keys: list[str]) -> list[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    commands = [
        "mkdir -p ~/.ssh",
        "chmod 700 ~/.ssh",
        f"echo '{authorized_keys_content}' > ~/.ssh/authorized_keys",
        "chmod 600 ~/.ssh/authorized_keys",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        (
            f"/usr/sbin/sshd -D -e -p {JUMP_POD_SSH_PORT}"
            " -o LogLevel=ERROR"
            " -o PasswordAuthentication=no"
            " -o AllowTcpForwarding=local"
        ),
    ]
    return commands


def _wait_for_load_balancer_address(
    api: client.CoreV1Api,
    namespace: str,
    service_name: str,
    timeout_seconds: int = 120,
) -> Optional[str]:
    start_time = time.time()
    while True:
        service = call_api_method(
            api.read_namespaced_service,
            expected=404,
            name=service_name,
            namespace=namespace,
        )
        if (
            service is not None
            and (service_status := service.status) is not None
            and (lb_status := service_status.load_balancer) is not None
            and (ingress_points := lb_status.ingress)
        ):
            ingress_point = ingress_points[0]
            # > Hostname is set for load-balancer ingress points that are DNS based (typically
            # > AWS load-balancers)
            # > IP is set for load-balancer ingress points that are IP based (typically GCE or
            # > OpenStack load-balancers)
            address = ingress_point.hostname or ingress_point.ip
            if address is not None:
                return address
        elapsed_time = time.time() - start_time
        if elapsed_time >= timeout_seconds:
            logger.warning("Timeout waiting for load balancer %s to get ip", service_name)
            return None
        time.sleep(1)


def _get_gateway_commands(
    authorized_keys: List[str], router: Optional[AnyRouterConfig] = None
) -> List[str]:
    authorized_keys_content = "\n".join(authorized_keys).strip()
    gateway_commands = " && ".join(get_dstack_gateway_commands(router=router))
    quoted_gateway_commands = shlex.quote(gateway_commands)

    commands = [
        # install packages
        "apt-get update && apt-get install -y sudo wget openssh-server nginx python3.10-venv libaugeas0",
        # install docker-systemctl-replacement
        "wget https://raw.githubusercontent.com/gdraheim/docker-systemctl-replacement/b18d67e521f0d1cf1d705dbb8e0416bef23e377c/files/docker/systemctl3.py -O /usr/bin/systemctl",
        "chmod a+rx /usr/bin/systemctl",
        # install certbot
        "python3 -m venv /root/certbotvenv/",
        "/root/certbotvenv/bin/pip install certbot-nginx",
        "ln -s /root/certbotvenv/bin/certbot /usr/bin/certbot",
        # prohibit password authentication
        'sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config',
        # set up ubuntu user
        "useradd -mUG sudo ubuntu",
        "echo 'ubuntu ALL=(ALL:ALL) NOPASSWD: ALL' | tee /etc/sudoers.d/ubuntu",
        # create ssh dirs and add public key
        "mkdir -p /run/sshd /home/ubuntu/.ssh",
        "chmod 700 /home/ubuntu/.ssh",
        f"echo '{authorized_keys_content}' > /home/ubuntu/.ssh/authorized_keys",
        "chmod 600 /home/ubuntu/.ssh/authorized_keys",
        "chown -R ubuntu:ubuntu /home/ubuntu/.ssh",
        # regenerate host keys
        "rm -rf /etc/ssh/ssh_host_*",
        "ssh-keygen -A > /dev/null",
        # start sshd
        "/usr/sbin/sshd -p 22 -o PermitUserEnvironment=yes",
        # run gateway
        f"su ubuntu -c {quoted_gateway_commands}",
        "sleep infinity",
    ]
    return commands


def _run_ssh_command(
    hostname: str, port: int, username: str, ssh_private_key: str, command: str
) -> tuple[int, bytes]:
    with tempfile.NamedTemporaryFile("w+", 0o600) as f:
        f.write(ssh_private_key)
        f.flush()
        proc = subprocess.run(
            [
                "ssh",
                "-F",
                "none",
                "-o",
                "StrictHostKeyChecking=no",
                "-i",
                f.name,
                "-p",
                str(port),
                f"{username}@{hostname}",
                command,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    return proc.returncode, proc.stdout


def _get_pod_service_name(pod_name: str) -> str:
    return f"{pod_name}-service"
