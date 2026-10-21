# How to add a new backend to dstack

The guide below explains the steps required to extend `dstack` with support for a new cloud provider.

## Overview of the process

1. Add the cloud provider to [gpuhunt](https://github.com/dstackai/gpuhunt)
2. Integrate the cloud provider into [dstack](https://github.com/dstackai/dstack)

## 1. Add a cloud provider to dstackai/gpuhunt

The [gpuhunt](https://github.com/dstackai/gpuhunt) project is a utility that `dstack` uses to collect information
about cloud providers, their supported machine configurations, pricing, etc. This information is later used by `dstack`
for provisioning machines.

Thus, in order to support a new cloud provider with `dstack`, you first need to add the cloud provider to `gpuhunt`.

To add a new cloud provider to `gpuhunt`, follow these steps:

### 1.1. Clone the repo

```bash
git clone https://github.com/dstackai/gpuhunt.git
```

### 1.2. Decide if you will implement an offline or an online provider

- **Offline providers** offer static machine configurations that are not frequently updated.
  `gpuhunt` collects offline providers' instance offers on an hourly basis.
  Examples: `aws`, `gcp`, `azure`, etc.
- **Online providers** offer dynamic machine configurations that are available at the very moment
  when you fetch configurations (e.g., GPU marketplaces).
  `gpuhunt` collects online providers' instance offers each time a `dstack` user provisions a new instance.
  Examples: `vastai`, `hotaisle`, etc.

### 1.3. Create the provider class

Create the provider class file under `src/gpuhunt/providers`.

Make sure your class extends either `OnlineProvider` or `OfflineProvider` from
[base.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/base.py),
matching the choice you made above.

Both kinds implement `get`, returning `CatalogItem`s with `provider` set to your provider's `NAME`.
Additionally:

- Online providers implement the `from_env` classmethod, which reads credentials from the
  environment with `get_creds_env` and raises `MissingCredsError` if one is missing. Providers that
  raise it are skipped by `default_catalog()` rather than failing the whole catalog.
- Offline providers may override `filter` to omit some offers from the published catalog.

Refer to examples:
- Offline providers:
  [verda.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/verda.py),
  [aws.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/aws.py),
  [azure.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/azure.py),
  [lambdalabs.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/lambdalabs.py).
- Online providers:
  [vultr.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/vultr.py),
  [hotaisle.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/hotaisle.py),
  [vastai.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/vastai.py).

### 1.4. Register the provider with the catalog

Add your provider in the following places:
- Either `OFFLINE_PROVIDERS` or `ONLINE_PROVIDERS` in `src/gpuhunt/_internal/catalog.py`.
- The `python -m gpuhunt` command in `src/gpuhunt/__main__.py`.
- (offline providers) The CI workflow in `.github/workflows/catalogs.yml`.
- (online providers) `ONLINE_PROVIDER_MODULES` in `src/gpuhunt/_internal/default.py`, which is what
  `default_catalog()` loads.

### 1.5. Add data quality tests

For offline providers, you can add data quality tests under `src/integrity_tests/`.
Data quality tests are run after collecting offline catalogs to ensure their integrity.

Refer to examples: [test_verda.py](https://github.com/dstackai/gpuhunt/blob/main/src/integrity_tests/test_verda.py),
[test_gcp.py](https://github.com/dstackai/gpuhunt/blob/main/src/integrity_tests/test_gcp.py).

### 1.6. Submit a pull request

Once the cloud provider is added, submit a pull request.

> Anything unclear? Ask questions on the [Discord server](https://discord.gg/u8SmfwPpMd).

## 2. Integrate the cloud provider to dstackai/dstack

Once the provider is added to `gpuhunt`, we can proceed with implementing
the corresponding backend with `dstack`. Follow the steps below.

### 2.1. Determine if you will implement a VM-based or a container-based backend

See the Appendix at the end of this document and make sure the provider meets the outlined requirements.

### 2.2. Set up the development environment

Follow [DEVELOPMENT.md](DEVELOPMENT.md).

### 2.3. Add dependencies to setup.py

Add any dependencies required by your cloud provider to `setup.py`. Create a separate section with the provider's name for these dependencies, and ensure that you update the `all` section to include them as well.

### 2.4. Add a new backend type

Add a new enumeration member for your provider to `BackendType` ([`src/dstack/_internal/core/models/backends/base.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/base.py)).

### 2.5. Create backend files and classes

`dstack` provides a helper script to generate all the necessary files and classes for a new backend.
To add a new backend named `ExampleXYZ`, you should run:

```shell
python scripts/add_backend.py -n ExampleXYZ
```

It will create an `examplexyz` backend directory under `src/dstack/_internal/core/backends` with the following files:

* `backend.py` with the `Backend` class implementation. You typically don't need to modify it.
* `compute.py` with the `Compute` class implementation. This is the core of the backend that you need to implement.
* `configurator.py` with the `Configurator` class implementation. It deals with validating and storing backend config. You need to adjust it with custom backend config validation.
* `models.py` with all the backend config models used by `Backend`, `Compute`, `Configurator` and other parts of `dstack`.

### 2.6. Adjust and register the backend config models

Go to `models.py`. It'll contain two config models required for all backends:

* `*BackendConfig` that contains all backend parameters available for user configuration except for creds.
* `*BackendConfigWithCreds` that contains all backends parameters available for user configuration and also creds.

Adjust generated config models by adding additional config parameters.
Typically you'd need to only modify the `*BackendConfig` model since other models extend it.

Then add these models to `AnyBackendConfig*` unions in [`src/dstack/_internal/core/backends/models.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/models.py).

The script also generates `*BackendStoredConfig` that extends `*BackendConfig` to be able to store extra parameters in the DB. By the same logic, it generates `*Config` that extends `*BackendStoredConfig` with creds and uses it as the main `Backend` and `Compute` config instead of using `*BackendConfigWithCreds` directly.

Refer to examples:
[verda](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/verda/models.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/models.py),
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/models.py),
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/models.py), etc.

### 2.7. Implement the backend compute class

Go to `compute.py` and implement `Compute` methods.
Optionally, extend and implement `ComputeWith*` classes to support additional features such as fleets, volumes, gateways, placement groups, etc. For example, extend `ComputeWithCreateInstanceSupport` to support fleets.
To support the cleanup of orphaned resources, extend `ComputeWithResourceListingSupport` as described in [Orphan cleanup support](#32-orphan-cleanup-support).

Refer to examples:
[verda](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/verda/compute.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/compute.py),
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/compute.py),
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/compute.py), etc.

### 2.8. Implement and register the configurator class

Go to `configurator.py` and implement custom `Configurator` logic. At minimum, you should implement creds validation.
You may also need to validate other config parameters if there are any.

Refer to examples: [verda](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/verda/configurator.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/configurator.py),
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/configurator.py),
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/configurator.py), etc.

Register configurator by appending it to `_CONFIGURATOR_CLASSES` in [`src/dstack/_internal/core/backends/configurators.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/configurators.py).

### 2.9. (Optional) Override provisioning timeout

If instances in the backend take more than 10 minutes to start, override the default provisioning timeout in
[`src/dstack/_internal/server/background/tasks/common.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/background/tasks/common.py).

### 2.10. Document the backend

Add the backend to the [Concepts->Backends](https://github.com/dstackai/dstack/blob/master/mkdocs/docs/concepts/backends.md
) page and the [server/comfig.yml](https://github.com/dstackai/dstack/blob/master/mkdocs/docs/reference/server/config.yml.md) reference.

## 3. Appendix

### 3.1. Backend compute type

`dstack` supports two types of backend compute:

- VM-based
- Container-based

#### 3.1.1. VM-based backend compute type

Used if the cloud provider allows provisioning virtual machines (VMs).
When `dstack` provisions a VM, it launches the `dstack-shim` agent inside the VM.
The agent controls the VM and starts Docker containers for users' jobs.

Since `dstack` controls the entire VM, VM-based backends can support more features,
such as blocks, instance volumes, privileged containers, and reusable instances.

Note, all VM-based backend `Compute`s should sublass the `ComputeWithPrivilegedSupport`
and `ComputeWithInstanceVolumesSupport` mixins, as the `dstack-shim` agent
provides these functionalities OOTB.

To support a VM-based backend, `dstack` expects the following:

- An API for creating and terminating VMs
- An external IP and a public port for SSH
- Cloud-init (preferred)
- VM images with Ubuntu, OpenSSH, GPU drivers, and Docker with NVIDIA runtime

For some VM-based backends, the `dstack` team also maintains
[custom VM images](../scripts/packer/README.md) with the required dependencies
and `dstack`-specific optimizations.

Examples of VM-based backends include: `aws`, `azure`, `gcp`, `lambda`, `verda`, etc.

#### 3.1.2. Container-based backend compute type

Used if the cloud provider only allows provisioning containers.
When `dstack` provisions a container, it launches the `dstack-runner` agent inside the container.
The agent accepts and runs users' jobs.

Since `dstack` doesn't control the underlying machine, container-based backends don't support some
`dstack` features, such as blocks, instance volumes, privileged containers, and reusable instances.

To support a container-based backend, `dstack` expects the following:

- An API for creating and terminating containers
- Containers properly configured to access GPUs
- An external IP and a public port for SSH
- A way to specify the Docker image
- A way to specify credentials for pulling images from private Docker registries
- A way to override the container entrypoint (at least ~2KB)
- A way to override the container user to root (as in `docker run --user root ...`)

Examples of container-based backends include: `kubernetes`, `vastai`, `runpod`.

### 3.2. Orphan cleanup support

`dstack` can find and delete cloud resources it created but no longer tracks, e.g. if the server
crashed after the provider created an instance but before it was recorded, or if instance
termination failed. The `OrphanCleanupPipeline` lists resources of backends that extend
`ComputeWithResourceListingSupport` and matches them with instances and jobs by `provider_ref`.

To support it in a backend:

1. Set `provider_ref` on every resource created for an instance or a job. It's
   `InstanceConfiguration.provider_ref` in `create_instance()` and `get_job_provider_ref(job)` in
   `run_job()`. Internal resources that outlive the instance if left behind (disks, keys, IPs)
   need it too, while resources deleted together with the instance don't.
    * If the provider supports tags, set the `PROVIDER_REF_TAG_KEY` tag and keep instance names as is.
      If the provider does not allow this key, use another one.
    * Otherwise, encode `provider_ref` in names with `generate_unique_instance_name(..., with_provider_ref=True)`
      and parse it with `parse_provider_ref_from_name()`.
    * Do not set it on resources of `run_jobs()` since orphan cleanup does not support compute groups yet.
2. Implement `list_resource_groups()`. It returns a `ListedResourceGroup` per provisioning attempt: the instance
   (`primary_id`) together with internal resources created for it. Skip resources without `provider_ref`.
   List resources of each region all or nothing: if any listing in a region fails, return no groups
   of the region and report it in `ResourceListing.failures`. Otherwise, a tracked instance's resources
   may be listed without the instance and deleted. Skip instances whose deletion is in progress
   (e.g. shutting down), but list their internal resources.
3. Implement `delete_resource_group()`. Delete everything in the group in the order the provider requires.
   The method must be idempotent and never delete resources that don't carry the group's `provider_ref`,
   such as attached volumes. If the deletion takes several steps, delete the instance first and raise
   `NotYetTerminated` instead of waiting for the next step, e.g. for the instance to be gone before its
   disk can be deleted. Next cleanups list the remaining internal resources and call the method again.

Refer to the [aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/compute.py) example.
