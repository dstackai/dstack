"""
Deterministic instances for the backend layer of the DB surface.

Kept out of `factories.py` because the backend models are one repetitive family — 19 backend
types plus 18 `*BackendData` blobs — and interleaving them with the core models would bury both.

Three `Text` columns are involved, one registry each:

- `BackendModel.config` holds `XStoredConfig(...).json()`, read back as the splice
  `XConfig(**json.loads(config), creds=XCreds.parse_raw(auth))`. The registries below keep the
  two halves apart the way the columns do, so a fixture matches one column's bytes exactly.
- `BackendModel.auth` holds `XCreds(...).json()`.
- `InstanceModel.backend_data` and `VolumeModel.backend_data` hold a `*BackendData` blob.
"""

from typing import Any, Callable

from dstack._internal.core.backends.aws.compute import (
    AWSGatewayBackendData,
    AWSInstanceBackendData,
    AWSVolumeBackendData,
)
from dstack._internal.core.backends.aws.models import (
    AWSAccessKeyCreds,
    AWSConfig,
    AWSCreds,
    AWSDefaultCreds,
    AWSOSImage,
    AWSOSImageConfig,
    AWSStoredConfig,
)
from dstack._internal.core.backends.azure.models import (
    AzureClientCreds,
    AzureConfig,
    AzureCreds,
    AzureDefaultCreds,
    AzureStoredConfig,
)
from dstack._internal.core.backends.cloudrift.models import (
    CloudRiftConfig,
    CloudRiftCreds,
    CloudRiftStoredConfig,
)
from dstack._internal.core.backends.crusoe.compute import (
    CrusoeInstanceBackendData,
    CrusoePlacementGroupBackendData,
)
from dstack._internal.core.backends.crusoe.models import (
    CrusoeConfig,
    CrusoeCreds,
    CrusoeStoredConfig,
)
from dstack._internal.core.backends.digitalocean_base.models import (
    BaseDigitalOceanConfig,
    BaseDigitalOceanCreds,
    BaseDigitalOceanStoredConfig,
)
from dstack._internal.core.backends.gcp.compute import (
    GCPOfferBackendData,
    GCPVolumeDiskBackendData,
)
from dstack._internal.core.backends.gcp.models import (
    GCPConfig,
    GCPCreds,
    GCPDefaultCreds,
    GCPServiceAccountCreds,
    GCPStoredConfig,
)
from dstack._internal.core.backends.hotaisle.compute import (
    HotAisleInstanceBackendData,
    HotAisleOfferBackendData,
)
from dstack._internal.core.backends.hotaisle.models import (
    HotAisleConfig,
    HotAisleCreds,
    HotAisleStoredConfig,
)
from dstack._internal.core.backends.jarvislabs.compute import JarvisLabsInstanceBackendData
from dstack._internal.core.backends.jarvislabs.models import (
    JarvisLabsConfig,
    JarvisLabsCreds,
    JarvisLabsStoredConfig,
)
from dstack._internal.core.backends.kubernetes.compute import KubernetesBackendData
from dstack._internal.core.backends.kubernetes.models import (
    KubeconfigConfig,
    KubernetesConfig,
    KubernetesContextConfig,
    KubernetesProxyJumpConfig,
    KubernetesStoredConfig,
)
from dstack._internal.core.backends.lambdalabs.models import (
    LambdaConfig,
    LambdaCreds,
    LambdaStoredConfig,
)
from dstack._internal.core.backends.nebius.compute import (
    NebiusClusterBackendData,
    NebiusInstanceBackendData,
    NebiusPlacementGroupBackendData,
)
from dstack._internal.core.backends.nebius.models import (
    NebiusConfig,
    NebiusCreds,
    NebiusStoredConfig,
)
from dstack._internal.core.backends.oci.models import (
    OCIClientCreds,
    OCIConfig,
    OCICreds,
    OCIDefaultCreds,
    OCIStoredConfig,
)
from dstack._internal.core.backends.runpod.compute import RunpodOfferBackendData
from dstack._internal.core.backends.runpod.models import (
    RunpodConfig,
    RunpodCreds,
    RunpodStoredConfig,
)
from dstack._internal.core.backends.slurm.models import (
    SlurmClusterConfigWithCreds,
    SlurmConfig,
    SlurmGPUPartitionConfig,
    SlurmPrivateKeyConfig,
    SlurmStoredConfig,
)
from dstack._internal.core.backends.vastai.compute import VastAIOfferBackendData
from dstack._internal.core.backends.vastai.models import (
    VastAIConfig,
    VastAICreds,
    VastAIStoredConfig,
)
from dstack._internal.core.backends.verda.compute import VerdaInstanceBackendData
from dstack._internal.core.backends.verda.models import (
    VerdaConfig,
    VerdaCreds,
    VerdaStoredConfig,
)
from dstack._internal.core.backends.vultr.models import (
    VultrConfig,
    VultrCreds,
    VultrStoredConfig,
)

# A PEM-shaped placeholder. Several backends store a private key inline in the `auth` column, and
# a one-word stand-in would not exercise the newlines that make those values awkward to encode.
_PRIVATE_KEY = (
    "-----BEGIN PRIVATE KEY-----\nMIIBVgIBADANBgkqhkiG9w0BAQEFAASC\n-----END PRIVATE KEY-----\n"
)
_SERVICE_ACCOUNT_JSON = (
    '{"type": "service_account", "project_id": "dstack-prod",'
    ' "private_key_id": "0123456789abcdef0123456789abcdef01234567"}'
)


# --- `BackendModel.config`: `XStoredConfig` -------------------------------------------------
# What the write path dumps into the column. The read side reconstructs an `XConfig` from these
# bytes plus the `auth` column, so it needs the class rather than an instance — see
# `BACKEND_CONFIG_MODELS` at the bottom.


def aws_stored_config() -> AWSStoredConfig:
    return AWSStoredConfig(
        regions=["us-east-1", "us-west-2"],
        vpc_name=None,
        vpc_ids={"us-east-1": "vpc-0a1b2c3d4e5f67890"},
        default_vpcs=False,
        public_ips=True,
        iam_instance_profile="dstack-instance-profile",
        tags={"env": "prod", "team": "ml"},
        os_images=AWSOSImageConfig(
            nvidia=AWSOSImage(
                name="dstack-nvidia-ubuntu-22.04", owner="123456789012", user="ubuntu"
            ),
        ),
        experimental_instance_types=["p5.48xlarge"],
    )


def azure_stored_config() -> AzureStoredConfig:
    return AzureStoredConfig(
        tenant_id="11111111-2222-3333-4444-555555555555",
        subscription_id="66666666-7777-8888-9999-000000000000",
        resource_group="dstack-rg",
        regions=["eastus", "westeurope"],
        vpc_ids={"eastus": "dstack-vnet"},
        subnet_ids={"eastus": "dstack-subnet"},
        public_ips=True,
        vm_managed_identity="dstack-identity",
        tags={"env": "prod"},
    )


def amddevcloud_stored_config() -> BaseDigitalOceanStoredConfig:
    return BaseDigitalOceanStoredConfig(
        type="amddevcloud", project_name="dstack", regions=["tor1"]
    )


def cloudrift_stored_config() -> CloudRiftStoredConfig:
    return CloudRiftStoredConfig(regions=["us-east-nc-nrp-1"])


def crusoe_stored_config() -> CrusoeStoredConfig:
    return CrusoeStoredConfig(
        project_id="a1b2c3d4-5678-4abc-9def-000000000000", regions=["us-east1"]
    )


def datacrunch_stored_config() -> VerdaStoredConfig:
    """`VerdaStoredConfig.type` is a two-value Literal, so both tags get a fixture."""
    return VerdaStoredConfig(type="datacrunch", regions=["FIN-01"])


def digitalocean_stored_config() -> BaseDigitalOceanStoredConfig:
    return BaseDigitalOceanStoredConfig(
        type="digitalocean", project_name="dstack", regions=["nyc3", "ams3"]
    )


def gcp_stored_config() -> GCPStoredConfig:
    return GCPStoredConfig(
        project_id="dstack-prod",
        regions=["us-central1", "europe-west4"],
        vpc_name="dstack-vpc",
        extra_vpcs=["dstack-extra-vpc"],
        roce_vpcs=["dstack-roce-vpc"],
        vpc_project_id="dstack-network",
        public_ips=True,
        nat_check=False,
        vm_service_account="dstack@dstack-prod.iam.gserviceaccount.com",
        tags={"env": "prod"},
        preview_features=["g4"],
    )


def hotaisle_stored_config() -> HotAisleStoredConfig:
    return HotAisleStoredConfig(team_handle="dstack-team", regions=["us-michigan-1"])


def jarvislabs_stored_config() -> JarvisLabsStoredConfig:
    return JarvisLabsStoredConfig(regions=["in-north-1"])


def kubernetes_stored_config() -> KubernetesStoredConfig:
    """
    One of the two backends whose creds live in the `config` column instead of `auth`, which the
    configurator writes as `auth=""`. So the kubeconfig is here rather than in a creds fixture.
    """
    return KubernetesStoredConfig(
        contexts=[
            KubernetesContextConfig(
                name="prod-cluster",
                proxy_jump=KubernetesProxyJumpConfig(hostname="10.0.0.1", port=22),
            ),
            "staging-cluster",
        ],
        proxy_jump=KubernetesProxyJumpConfig(hostname="bastion.internal", port=2222),
        namespace="dstack",
        kubeconfig=KubeconfigConfig(filename="", data="apiVersion: v1\nkind: Config\n"),
    )


def lambdalabs_stored_config() -> LambdaStoredConfig:
    return LambdaStoredConfig(regions=["us-east-1", "us-west-2"])


def nebius_stored_config() -> NebiusStoredConfig:
    return NebiusStoredConfig(
        projects=["project-e00dstack"],
        regions=["eu-north1"],
        fabrics=["fabric-3"],
        tags={"env": "prod"},
    )


def oci_stored_config() -> OCIStoredConfig:
    return OCIStoredConfig(
        regions=["eu-frankfurt-1"],
        compartment_id="ocid1.compartment.oc1..aaaaaaaadstack",
        subnet_ids_per_region={"eu-frankfurt-1": "ocid1.subnet.oc1.eu-frankfurt-1.aaaaaaaadstack"},
    )


def runpod_stored_config() -> RunpodStoredConfig:
    return RunpodStoredConfig(regions=["US-KS-2", "EU-RO-1"], community_cloud=True)


def slurm_stored_config() -> SlurmStoredConfig:
    """The other creds-in-`config` backend: the SSH private key is part of the cluster config."""
    return SlurmStoredConfig(
        clusters=[
            SlurmClusterConfigWithCreds(
                name="hpc-1",
                gpu_partitions=[
                    SlurmGPUPartitionConfig(gpu="H100", partitions=["gpu", "gpu-long"])
                ],
                cpu_partitions=["cpu"],
                hostname="login.hpc.example.com",
                port=22,
                user="dstack",
                private_key=SlurmPrivateKeyConfig(path="", content=_PRIVATE_KEY),
            )
        ]
    )


def vastai_stored_config() -> VastAIStoredConfig:
    return VastAIStoredConfig(regions=["Poland", "Sweden"], community_cloud=False)


def verda_stored_config() -> VerdaStoredConfig:
    return VerdaStoredConfig(type="verda", regions=["ICE-01"])


def vultr_stored_config() -> VultrStoredConfig:
    return VultrStoredConfig(regions=["ewr", "ams"])


# --- `BackendModel.auth`: `XCreds` ------------------------------------------------------------
# A fixture PER UNION ARM for the four custom-root unions. Building the union once only ever
# exercises the arm that happens to match first, and which arm matches is exactly what changes
# when v2 resolves unions in smart mode instead of left to right.
#
# `kubernetes` and `slurm` are absent on purpose: their configurators write `auth=""` and keep
# creds in the `config` column, so there is no blob here to be compatible with.


def aws_creds_access_key() -> AWSCreds:
    return AWSCreds.parse_obj(
        {"type": "access_key", "access_key": "AKIAIOSFODNN7EXAMPLE", "secret_key": "wJalrXUtnFEMI"}
    )


def aws_creds_default() -> AWSCreds:
    return AWSCreds.parse_obj({"type": "default"})


def azure_creds_client() -> AzureCreds:
    return AzureCreds.parse_obj(
        {
            "type": "client",
            "client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "client_secret": "azure-client-secret",
            "tenant_id": "11111111-2222-3333-4444-555555555555",
        }
    )


def azure_creds_default() -> AzureCreds:
    return AzureCreds.parse_obj({"type": "default"})


def gcp_creds_service_account() -> GCPCreds:
    return GCPCreds.parse_obj(
        {"type": "service_account", "filename": "", "data": _SERVICE_ACCOUNT_JSON}
    )


def gcp_creds_default() -> GCPCreds:
    return GCPCreds.parse_obj({"type": "default"})


def oci_creds_client() -> OCICreds:
    return OCICreds.parse_obj(
        {
            "type": "client",
            "user": "ocid1.user.oc1..aaaaaaaadstack",
            "tenancy": "ocid1.tenancy.oc1..aaaaaaaadstack",
            "key_content": _PRIVATE_KEY,
            "fingerprint": "12:34:56:78:9a:bc:de:f0:12:34:56:78:9a:bc:de:f0",
            "region": "eu-frankfurt-1",
        }
    )


def oci_creds_default() -> OCICreds:
    return OCICreds.parse_obj({"type": "default"})


def cloudrift_creds() -> CloudRiftCreds:
    return CloudRiftCreds(api_key="rift-api-key")


def crusoe_creds() -> CrusoeCreds:
    return CrusoeCreds(access_key="crusoe-access-key", secret_key="crusoe-secret-key")


def digitalocean_creds() -> BaseDigitalOceanCreds:
    """Shared by the `digitalocean` and `amddevcloud` backends, which store the same shape."""
    return BaseDigitalOceanCreds(api_key="dop_v1_digitalocean")


def hotaisle_creds() -> HotAisleCreds:
    return HotAisleCreds(api_key="hotaisle-api-key")


def jarvislabs_creds() -> JarvisLabsCreds:
    return JarvisLabsCreds(api_key="jarvislabs-api-key")


def lambdalabs_creds() -> LambdaCreds:
    return LambdaCreds(api_key="lambda-api-key")


def nebius_creds() -> NebiusCreds:
    return NebiusCreds(
        service_account_id="serviceaccount-e00dstack",
        public_key_id="publickey-e00dstack",
        private_key_content=_PRIVATE_KEY,
    )


def runpod_creds() -> RunpodCreds:
    return RunpodCreds(api_key="runpod-api-key")


def vastai_creds() -> VastAICreds:
    return VastAICreds(api_key="vastai-api-key")


def verda_creds() -> VerdaCreds:
    """Also covers `datacrunch`, which shares the creds model and differs only in config `type`."""
    return VerdaCreds(client_id="verda-client-id", client_secret="verda-secret")


def vultr_creds() -> VultrCreds:
    return VultrCreds(api_key="vultr-api-key")


# --- `backend_data` columns: `*BackendData` ---------------------------------------------------
# `InstanceModel.backend_data` and `VolumeModel.backend_data`. These are the smallest models in
# the codebase and the least reviewed, which is why they get a fixture each rather than a
# representative sample: a wrong read here silently loses the handle to a live cloud resource.
#
# `NebiusOfferBackendData` is absent — its `fabrics: set[str]` cannot be dumped at all today. See
# `TestNebiusOfferBackendDataSetField` in the test modules.


def aws_gateway_backend_data() -> AWSGatewayBackendData:
    return AWSGatewayBackendData(
        lb_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/net/dstack/1a2b",
        tg_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/dstack/3c4d",
        listener_arn="arn:aws:elasticloadbalancing:us-east-1:123456789012:listener/net/dstack/5e6f",
        http_listener_arn=None,
    )


def aws_instance_backend_data() -> AWSInstanceBackendData:
    return AWSInstanceBackendData(eip_allocation_id="eipalloc-0a1b2c3d4e5f67890")


def aws_volume_backend_data() -> AWSVolumeBackendData:
    return AWSVolumeBackendData(volume_type="gp3", iops=3000)


def crusoe_instance_backend_data() -> CrusoeInstanceBackendData:
    return CrusoeInstanceBackendData(data_disk_id="a1b2c3d4-5678-4abc-9def-000000000001")


def crusoe_placement_group_backend_data() -> CrusoePlacementGroupBackendData:
    return CrusoePlacementGroupBackendData(
        ib_partition_id="a1b2c3d4-5678-4abc-9def-000000000002",
        ib_network_id="a1b2c3d4-5678-4abc-9def-000000000003",
    )


def gcp_offer_backend_data() -> GCPOfferBackendData:
    return GCPOfferBackendData(is_dws_calendar_mode=True)


def gcp_volume_disk_backend_data() -> GCPVolumeDiskBackendData:
    return GCPVolumeDiskBackendData(disk_type="pd-balanced")


def hotaisle_instance_backend_data() -> HotAisleInstanceBackendData:
    return HotAisleInstanceBackendData(ip_address="203.0.113.10")


def hotaisle_offer_backend_data() -> HotAisleOfferBackendData:
    """`vm_specs: Mapping[str, Any]` — an untyped passthrough, so the values ride through as-is."""
    return HotAisleOfferBackendData(
        vm_specs={"cpu": {"count": 26}, "gpu": {"count": 1, "model": "MI300X"}, "ram": 224}
    )


def jarvislabs_instance_backend_data() -> JarvisLabsInstanceBackendData:
    return JarvisLabsInstanceBackendData(ssh_key_ids=["1234", "5678"])


def kubernetes_backend_data() -> KubernetesBackendData:
    return KubernetesBackendData(
        jump_pod_name="dstack-jump-pod",
        jump_pod_service_name="dstack-jump-pod-service",
        user_ssh_public_key="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQD dstack@localhost",
    )


def nebius_cluster_backend_data() -> NebiusClusterBackendData:
    return NebiusClusterBackendData(id="computecluster-e00dstack", fabric="fabric-3")


def nebius_instance_backend_data() -> NebiusInstanceBackendData:
    return NebiusInstanceBackendData(boot_disk_id="computedisk-e00dstack")


def nebius_placement_group_backend_data() -> NebiusPlacementGroupBackendData:
    return NebiusPlacementGroupBackendData(cluster=nebius_cluster_backend_data())


def runpod_offer_backend_data() -> RunpodOfferBackendData:
    return RunpodOfferBackendData(pod_counts=[1, 2, 4, 8])


def vastai_offer_backend_data() -> VastAIOfferBackendData:
    return VastAIOfferBackendData(min_bid=0.1234)


def verda_instance_backend_data() -> VerdaInstanceBackendData:
    return VerdaInstanceBackendData(
        startup_script_id="a1b2c3d4-5678-4abc-9def-000000000004",
        ssh_key_ids=["a1b2c3d4-5678-4abc-9def-000000000005"],
    )


# --- Registries -------------------------------------------------------------------------------
# Keys are the fixture names. A backend appears under its `BackendType` value rather than its
# module name, so `lambdalabs` reads as `lambda` and `digitalocean_base` splits into the two
# backends that share it.

BACKEND_STORED_CONFIGS: dict[str, Callable[[], Any]] = {
    "amddevcloud": amddevcloud_stored_config,
    "aws": aws_stored_config,
    "azure": azure_stored_config,
    "cloudrift": cloudrift_stored_config,
    "crusoe": crusoe_stored_config,
    "datacrunch": datacrunch_stored_config,
    "digitalocean": digitalocean_stored_config,
    "gcp": gcp_stored_config,
    "hotaisle": hotaisle_stored_config,
    "jarvislabs": jarvislabs_stored_config,
    "kubernetes": kubernetes_stored_config,
    "lambda": lambdalabs_stored_config,
    "nebius": nebius_stored_config,
    "oci": oci_stored_config,
    "runpod": runpod_stored_config,
    "slurm": slurm_stored_config,
    "vastai": vastai_stored_config,
    "verda": verda_stored_config,
    "vultr": vultr_stored_config,
}

BACKEND_CREDS: dict[str, Callable[[], Any]] = {
    "aws.access_key": aws_creds_access_key,
    "aws.default": aws_creds_default,
    "azure.client": azure_creds_client,
    "azure.default": azure_creds_default,
    "cloudrift": cloudrift_creds,
    "crusoe": crusoe_creds,
    "digitalocean": digitalocean_creds,
    "gcp.default": gcp_creds_default,
    "gcp.service_account": gcp_creds_service_account,
    "hotaisle": hotaisle_creds,
    "jarvislabs": jarvislabs_creds,
    "lambda": lambdalabs_creds,
    "nebius": nebius_creds,
    "oci.client": oci_creds_client,
    "oci.default": oci_creds_default,
    "runpod": runpod_creds,
    "vastai": vastai_creds,
    "verda": verda_creds,
    "vultr": vultr_creds,
}

BACKEND_DATA: dict[str, Callable[[], Any]] = {
    "aws_gateway": aws_gateway_backend_data,
    "aws_instance": aws_instance_backend_data,
    "aws_volume": aws_volume_backend_data,
    "crusoe_instance": crusoe_instance_backend_data,
    "crusoe_placement_group": crusoe_placement_group_backend_data,
    "gcp_offer": gcp_offer_backend_data,
    "gcp_volume_disk": gcp_volume_disk_backend_data,
    "hotaisle_instance": hotaisle_instance_backend_data,
    "hotaisle_offer": hotaisle_offer_backend_data,
    "jarvislabs_instance": jarvislabs_instance_backend_data,
    "kubernetes": kubernetes_backend_data,
    "nebius_cluster": nebius_cluster_backend_data,
    "nebius_instance": nebius_instance_backend_data,
    "nebius_placement_group": nebius_placement_group_backend_data,
    "runpod_offer": runpod_offer_backend_data,
    "vastai_offer": vastai_offer_backend_data,
    "verda_instance": verda_instance_backend_data,
}

# The model each `backend_config` fixture is read back as. Parsing needs the class, and taking it
# off the factory would tie the read to whichever arm the factory picked.
BACKEND_CONFIG_MODELS: dict[str, Any] = {
    "amddevcloud": BaseDigitalOceanConfig,
    "aws": AWSConfig,
    "azure": AzureConfig,
    "cloudrift": CloudRiftConfig,
    "crusoe": CrusoeConfig,
    "datacrunch": VerdaConfig,
    "digitalocean": BaseDigitalOceanConfig,
    "gcp": GCPConfig,
    "hotaisle": HotAisleConfig,
    "jarvislabs": JarvisLabsConfig,
    "kubernetes": KubernetesConfig,
    "lambda": LambdaConfig,
    "nebius": NebiusConfig,
    "oci": OCIConfig,
    "runpod": RunpodConfig,
    "slurm": SlurmConfig,
    "vastai": VastAIConfig,
    "verda": VerdaConfig,
    "vultr": VultrConfig,
}

BACKEND_CREDS_MODELS: dict[str, Any] = {
    "aws.access_key": AWSCreds,
    "aws.default": AWSCreds,
    "azure.client": AzureCreds,
    "azure.default": AzureCreds,
    "cloudrift": CloudRiftCreds,
    "crusoe": CrusoeCreds,
    "digitalocean": BaseDigitalOceanCreds,
    "gcp.default": GCPCreds,
    "gcp.service_account": GCPCreds,
    "hotaisle": HotAisleCreds,
    "jarvislabs": JarvisLabsCreds,
    "lambda": LambdaCreds,
    "nebius": NebiusCreds,
    "oci.client": OCICreds,
    "oci.default": OCICreds,
    "runpod": RunpodCreds,
    "vastai": VastAICreds,
    "verda": VerdaCreds,
    "vultr": VultrCreds,
}

# Named so the arm tests can assert on the resolved arm rather than only on the dump.
CREDS_ARMS: dict[str, Any] = {
    "aws.access_key": AWSAccessKeyCreds,
    "aws.default": AWSDefaultCreds,
    "azure.client": AzureClientCreds,
    "azure.default": AzureDefaultCreds,
    "gcp.default": GCPDefaultCreds,
    "gcp.service_account": GCPServiceAccountCreds,
    "oci.client": OCIClientCreds,
    "oci.default": OCIDefaultCreds,
}
