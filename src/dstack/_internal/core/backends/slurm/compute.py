import concurrent.futures
import contextlib
import shlex
import time
from functools import partial
from typing import Optional

from dstack._internal.core.backends.base.compute import (
    Compute,
    ComputeWithAllOffersCached,
    ComputeWithGroupProvisioningSupport,
    ComputeWithMultinodeSupport,
    generate_unique_backend_name,
    get_docker_commands,
    normalize_arch,
)
from dstack._internal.core.backends.base.models import JobConfiguration
from dstack._internal.core.backends.base.offers import OfferModifier, RegionalSkipOfferCache
from dstack._internal.core.backends.slurm.cluster import (
    SlurmCluster,
    get_clusters_from_backend_config,
)
from dstack._internal.core.backends.slurm.models import SlurmConfig
from dstack._internal.core.backends.slurm.resources import (
    GPUModel,
    Node,
    RequestedResources,
    get_requested_resources_from_resources_spec,
    parse_gres_gpu_count,
)
from dstack._internal.core.consts import DSTACK_RUNNER_SSH_PORT
from dstack._internal.core.errors import ComputeError, SkipOffer
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.compute_groups import ComputeGroup, ComputeGroupProvisioningData
from dstack._internal.core.models.instances import (
    Disk,
    Gpu,
    InstanceAvailability,
    InstanceOfferWithAvailability,
    InstanceRuntime,
    InstanceType,
    Resources,
    SSHConnectionParams,
)
from dstack._internal.core.models.placement import PlacementGroup
from dstack._internal.core.models.runs import Job, JobProvisioningData, Requirements, Run
from dstack._internal.core.models.volumes import Volume
from dstack._internal.utils.docker import is_default_registry, parse_image_name
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)

# An arbitrarily chosen sane limit; not enforced by Slurm
SLURM_JOB_NAME_MAX_LENGTH = 64

SLURM_JOB_OUTPUT = "/dev/null"

PROVISIONING_TIMEOUT = 60

PRE_RUNNER_COMMANDS = [
    # enroot creates the rootfs directory group-writable but OpenSSH in strict mode requires
    # all directories in the authorized_keys path not be group or world writable.
    "chmod 0755 /",
    # enroot is an unprivileged single-user runtime, where the user from the parent user ns
    # (the one who starts the container) is mapped to either UID 0 (our case; we use
    # Pyxis's --container-remap-root option, which is translated to enroot's --root option)
    # or the same UID.
    # OpenSSH cannot operate in such an environment (without tweaking build-time options)
    # as it requires a separate unprivileged account (SSH_PRIVSEP_USER build-time option,
    # sshd by default) for the privsep feature.
    # We work around this limitation by replacing the privsep account with root.
    "sed -i '/^sshd:/d' /etc/passwd",
    "echo 'sshd:x:0:0:privsep:/dev/null:/sbin/nologin' >> /etc/passwd",
]


class SlurmCompute(
    ComputeWithAllOffersCached,
    ComputeWithMultinodeSupport,
    ComputeWithGroupProvisioningSupport,
    Compute,
):
    def __init__(self, config: SlurmConfig):
        super().__init__()
        self._region_to_cluster_map = {
            c.region: c for c in get_clusters_from_backend_config(config)
        }
        # NB: The current implementation of RegionalSkipOfferCache is suitable despite of
        # lack of zones (partitions) support since it tracks unique runs (identified by Run.id),
        # not their requirements, thus we only skip offers within the same run (-> the same
        # configuration -> the same zones)
        self._skip_offer_cache = RegionalSkipOfferCache(ttl=60)

    def get_all_offers_with_availability(self) -> list[InstanceOfferWithAvailability]:
        offers: list[InstanceOfferWithAvailability] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            future_to_cluster_map: dict[
                concurrent.futures.Future[list[InstanceOfferWithAvailability]], SlurmCluster
            ] = {}
            for cluster in self._region_to_cluster_map.values():
                future = executor.submit(_get_cluster_offers, cluster)
                future_to_cluster_map[future] = cluster
            for future in concurrent.futures.as_completed(future_to_cluster_map):
                try:
                    cluster_offers = future.result()
                except ComputeError as e:
                    logger.warning(
                        "Failed to get offers from cluster %s: %s: %s",
                        future_to_cluster_map[future],
                        e.__class__.__name__,
                        e,
                    )
                    continue
                offers.extend(cluster_offers)
        return offers

    def get_offers_modifiers(
        self, requirements: Requirements, full_offers: bool
    ) -> list[OfferModifier]:
        if full_offers:
            return []
        requested_resources = get_requested_resources_from_resources_spec(requirements.resources)
        return [partial(self._offer_modifier, requested_resources)]

    def run_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        volumes: list[Volume],
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
    ) -> JobProvisioningData:
        compute_provisioning_data = self._run_slurm_job(
            run=run,
            job=job,
            instance_offer=instance_offer,
            project_ssh_public_key=project_ssh_public_key,
            requirements=requirements,
        )
        return compute_provisioning_data.job_provisioning_datas[0]

    def run_jobs(
        self,
        run: Run,
        job_configurations: list[JobConfiguration],
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        project_ssh_private_key: str,
        placement_group: Optional[PlacementGroup],
        requirements: Requirements,
    ) -> ComputeGroupProvisioningData:
        master_job = job_configurations[0].job
        return self._run_slurm_job(
            run=run,
            job=master_job,
            instance_offer=instance_offer,
            project_ssh_public_key=project_ssh_public_key,
            requirements=requirements,
        )

    def terminate_instance(
        self, instance_id: str, region: str, backend_data: Optional[str] = None
    ):
        _, slurm_job_id, _ = _parse_instance_id(instance_id)
        with self._get_cluster(region).get_client() as client:
            client.cancel_job(slurm_job_id)

    def terminate_compute_group(self, compute_group: ComputeGroup):
        region = compute_group.provisioning_data.region
        slurm_job_id = compute_group.provisioning_data.compute_group_id
        with self._get_cluster(region).get_client() as client:
            client.cancel_job(slurm_job_id)

    def _run_slurm_job(
        self,
        run: Run,
        job: Job,
        instance_offer: InstanceOfferWithAvailability,
        project_ssh_public_key: str,
        requirements: Requirements,
    ) -> ComputeGroupProvisioningData:
        if job.job_spec.registry_auth is not None:
            self._skip_offer_cache.add(run, job, instance_offer)
            raise ComputeError("Private registries are not supported yet")

        region = instance_offer.region
        cluster = self._get_cluster(region)
        if self._skip_offer_cache.check(run, job, instance_offer):
            raise SkipOffer(f"Cluster {cluster} has recently failed to schedule a similar job")
        with (
            cluster.get_client() as client,
            contextlib.ExitStack() as exit_stack,
        ):
            assert run.run_spec.run_name is not None
            slurm_job_name = generate_unique_backend_name(
                resource_name=run.run_spec.run_name,
                project_name=run.project_name,
                max_length=SLURM_JOB_NAME_MAX_LENGTH,
            )

            assert run.run_spec.ssh_key_pub is not None
            authorized_keys = [project_ssh_public_key.strip(), run.run_spec.ssh_key_pub.strip()]

            node_count = job.job_spec.jobs_per_replica
            resources_spec = requirements.resources
            requested_resources = get_requested_resources_from_resources_spec(resources_spec)

            partitions = _get_cluster_partitions(cluster, requested_resources)
            if requested_resources.gpu_count > 0:
                assert resources_spec.gpu is not None
                partitions = partitions & cluster.filter_gpu_partitions(resources_spec.gpu)
                logger.debug("Matching GPU partitions: %s", partitions)
            else:
                logger.debug("CPU partitions: %s", partitions)
            requested_partitions = run.run_spec.configuration.availability_zones
            if requested_partitions is not None:
                partitions = partitions & set(requested_partitions)
                logger.debug("Filtered partitions: %s", partitions)
            if not partitions:
                self._skip_offer_cache.add(run, job, instance_offer)
                raise ComputeError("No matching partitions found")

            script_commands: list[str] = ["set -eu"]
            sbatch_directives = [
                f"#SBATCH --job-name={slurm_job_name}",
                f"#SBATCH --output={SLURM_JOB_OUTPUT}",
                "#SBATCH --no-requeue",
                f"#SBATCH --partition={','.join(partitions)}",
                f"#SBATCH --nodes={node_count}",
                "#SBATCH --ntasks-per-node=1",
                f"#SBATCH --cpus-per-task={requested_resources.cpu_count}",
                f"#SBATCH --mem={requested_resources.memory_mib}M",
            ]
            srun_options = [
                f"--cpus-per-task={requested_resources.cpu_count}",
                f"--container-image={_build_image_uri(job.job_spec.image_name)}",
                f"--container-name={slurm_job_name}",
                "--container-remap-root",
                "--container-writable",
                "--no-container-mount-home",
            ]
            if requested_resources.gpu_count > 0:
                sbatch_directives.append(f"#SBATCH --gres=gpu:{requested_resources.gpu_count}")
            else:
                # Force skip enroot's nvidia hook on CPU nodes even if NVIDIA_VISIBLE_DEVICES
                # is set in the image to avoid failure:
                # > nvidia-container-cli: initialization error: nvml error: driver not loaded
                # > [ERROR] /etc/enroot/hooks.d/98-nvidia.sh exited with return code 1
                script_commands.append("export NVIDIA_VISIBLE_DEVICES=void")
                srun_options.append("--container-env=NVIDIA_VISIBLE_DEVICES")
            dstack_commands = get_docker_commands(
                authorized_keys=authorized_keys, pre_runner_commands=PRE_RUNNER_COMMANDS
            )
            srun_command = ["srun"] + srun_options + ["sh", "-c", " && ".join(dstack_commands)]
            script_commands.append(shlex.join(srun_command))
            script_lines: list[str] = ["#!/bin/sh"] + sbatch_directives + script_commands

            slurm_job_id = client.submit_batch_script("\n".join(script_lines))
            exit_stack.callback(client.cancel_job, slurm_job_id)

            submitted_at = time.monotonic()
            job_state: Optional[str] = None
            while time.monotonic() - submitted_at < PROVISIONING_TIMEOUT:
                job_state = client.get_job_state(slurm_job_id)
                logger.debug("slurm_job_id: %s, state: %s", slurm_job_id, job_state)
                if job_state is None:
                    self._skip_offer_cache.add(run, job, instance_offer)
                    raise ComputeError(
                        f"Slurm job {slurm_job_id} not found. It either failed or was canceled"
                    )
                if job_state.upper() == "RUNNING":
                    break
                time.sleep(1)
            else:
                self._skip_offer_cache.add(run, job, instance_offer)
                raise ComputeError(
                    f"Slurm job {slurm_job_id} didn't start in {PROVISIONING_TIMEOUT} seconds."
                    f" Last state: {job_state}"
                )

            job_nodes = client.get_job_nodes(slurm_job_id)
            if len(job_nodes) != node_count:
                raise ComputeError(f"Node count mismatch: len({job_nodes}) != {node_count}")
            job_partition = client.get_job_partition(slurm_job_id)

            jpds = [
                JobProvisioningData(
                    backend=BackendType.SLURM,
                    instance_type=_build_instance_type(cluster, job_node, requested_resources),
                    instance_id=_build_instance_id(slurm_job_name, slurm_job_id, job_node.name),
                    hostname=job_node.hostname,
                    internal_ip=job_node.ip,
                    region=region,
                    availability_zone=job_partition,
                    price=0.0,
                    username="root",
                    ssh_port=DSTACK_RUNNER_SSH_PORT,
                    dockerized=False,
                    ssh_proxy=SSHConnectionParams(
                        hostname=cluster.hostname,
                        port=cluster.port,
                        username=cluster.user,
                    ),
                    backend_data=None,
                )
                for job_node in job_nodes
            ]

            res = client.exec(f"""
                set -eu
                if [ ! -e ~/.ssh/authorized_keys ]; then
                    mkdir -p ~/.ssh
                    chmod 700 ~/.ssh
                    touch ~/.ssh/authorized_keys
                    chmod 600 ~/.ssh/authorized_keys
                fi
                for key in {shlex.join(authorized_keys)}; do
                    if ! grep -qF "$key" ~/.ssh/authorized_keys; then
                        echo 'command="/bin/false"' "$key" >> ~/.ssh/authorized_keys
                    fi
                done
            """)
            if not res.ok:
                raise ComputeError(f"Failed to add authorized keys: {res}")

            exit_stack.pop_all()

            return ComputeGroupProvisioningData(
                compute_group_id=slurm_job_id,
                compute_group_name=slurm_job_name,
                backend=BackendType.SLURM,
                region=region,
                job_provisioning_datas=jpds,
            )

    def _offer_modifier(
        self,
        requested_resources: RequestedResources,
        offer: InstanceOfferWithAvailability,
    ) -> Optional[InstanceOfferWithAvailability]:
        resources = offer.instance.resources
        if (
            resources.cpus < requested_resources.cpu_count
            or resources.memory_mib < requested_resources.memory_mib
            or len(resources.gpus) < requested_resources.gpu_count
        ):
            return None

        cluster = self._get_cluster(offer.region)
        partitions = _get_cluster_partitions(cluster, requested_resources)
        assert offer.availability_zones is not None
        filtered_partitions = set(offer.availability_zones) & partitions
        if not filtered_partitions:
            return None

        offer_copy = offer.copy(deep=True)
        _adjust_resources(offer_copy.instance.resources, requested_resources)
        offer_copy.availability_zones = list(filtered_partitions)
        return offer_copy

    def _get_cluster(self, region: str) -> SlurmCluster:
        try:
            return self._region_to_cluster_map[region]
        except KeyError:
            raise ComputeError(f"Unknown region: {region!r}")


def _get_cluster_offers(cluster: SlurmCluster) -> list[InstanceOfferWithAvailability]:
    nodes = cluster.get_discovered_nodes()
    return [
        InstanceOfferWithAvailability(
            backend=BackendType.SLURM,
            instance=_build_instance_type(cluster, node),
            region=cluster.region,
            price=0.0,
            availability=InstanceAvailability.UNKNOWN,
            availability_zones=node.partitions,
            instance_runtime=InstanceRuntime.RUNNER,
        )
        for node in nodes
    ]


def _get_cluster_partitions(
    cluster: SlurmCluster, requested_resources: RequestedResources
) -> set[str]:
    discovered_partitions = cluster.get_discovered_partitions()
    if requested_resources.gpu_count > 0:
        gpu_partitions = cluster.get_gpu_partitions()
        return discovered_partitions & gpu_partitions
    cpu_partitions = cluster.get_cpu_partitions()
    if cpu_partitions is not None:
        return discovered_partitions & cpu_partitions
    cpu_partitions = discovered_partitions - cluster.get_gpu_partitions()
    return cpu_partitions


def _build_instance_type(
    cluster: SlurmCluster, node: Node, requested_resources: Optional[RequestedResources] = None
) -> InstanceType:
    gpus: list[Gpu] = []
    gpu_count: int = 0
    for gres in node.gres:
        try:
            gpu_count += parse_gres_gpu_count(gres)
        except ValueError as e:
            logger.warning("Failed to parse GPU GRES: %s: %s", node, e)
    if gpu_count > 0:
        node_gpu_models: set[GPUModel] = set()
        for partition in node.partitions:
            gpu_model = cluster.get_partition_gpu_model(partition)
            if gpu_model is not None:
                node_gpu_models.add(gpu_model)
        if not node_gpu_models:
            logger.warning("GPU GRES found but not mapped: %s", node)
        elif len(node_gpu_models) > 1:
            logger.warning("Multiple GPU models mapped: %s: %s", node, node_gpu_models)
        else:
            gpu = next(iter(node_gpu_models)).to_gpu()
            gpus = [gpu] * gpu_count

    try:
        cpu_arch = normalize_arch(node.arch).to_cpu_architecture()
    except ValueError as e:
        logger.warning("Failed to normalize CPU arch: %s: %s", node, e)
        cpu_arch = None

    instance_type = InstanceType(
        name=node.name,
        resources=Resources(
            cpu_arch=cpu_arch,
            cpus=node.cpus,
            memory_mib=node.memory_mib,
            gpus=gpus,
            spot=False,
            disk=Disk(size_mib=0),
        ),
    )
    if requested_resources is not None:
        # NB: unconditionally updates resources, may set values higher than the current ones
        _adjust_resources(instance_type.resources, requested_resources)
    return instance_type


def _adjust_resources(resources: Resources, requested_resources: RequestedResources) -> None:
    resources.cpus = requested_resources.cpu_count
    resources.memory_mib = requested_resources.memory_mib
    resources.gpus = resources.gpus[: requested_resources.gpu_count]
    resources.disk = Disk(size_mib=requested_resources.disk_mib)


def _build_image_uri(image_name: str) -> str:
    # https://github.com/NVIDIA/pyxis/wiki/Usage#image-uri-formats
    image = parse_image_name(image_name)
    image_uri: str
    if image.digest is not None:
        image_uri = f"{image.repo}@{image.digest}"
    else:
        image_uri = f"{image.repo}:{image.tag}"
    registry = image.registry
    if registry is not None and is_default_registry(registry):
        registry = None
    if registry is not None:
        image_uri = f"{registry}#{image_uri}"
    return image_uri


def _build_instance_id(slurm_job_name: str, slurm_job_id: str, node_name: str) -> str:
    return f"{slurm_job_name}:{slurm_job_id}:{node_name}"


def _parse_instance_id(compute_group_id: str) -> tuple[str, str, str]:
    slurm_job_name, slurm_job_id, node_name = compute_group_id.split(":", maxsplit=2)
    return slurm_job_name, slurm_job_id, node_name
