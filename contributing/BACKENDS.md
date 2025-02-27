# How to add a new backend to dstack

The guide below explains the steps required to extend `dstack` with support for a new cloud provider.

## Overview of the process

1. Add the cloud provider to [gpuhunt](https://https://github.com/dstackai/gpuhunt)
2. Integrate the cloud provider into [dstack](https://https://github.com/dstackai/dstack)

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
  Examples: `tensordock`, `vastai`, etc.

### 1.3. Create the provider class

Create the provider class file under `src/gpuhunt/providers`. 

Make sure your class extends the [`AbstractProvider`](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/__init__.py)
base class. See its docstrings for descriptions of the methods that your class should implement.

Refer to examples:
- Offline providers:
  [datacrunch.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/datacrunch.py),
  [aws.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/aws.py),
  [azure.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/azure.py),
  [lambdalabs.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/lambdalabs.py).
- Online providers:
  [vultr.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/vultr.py)
  [tensordock.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/tensordock.py),
  [vastai.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/vastai.py).

### 1.4. Register the provider with the catalog

Add your provider in the following places:
- Either `OFFLINE_PROVIDERS` or `ONLINE_PROVIDERS` in `src/gpuhunt/_internal/catalog.py`.
- The `python -m gpuhunt` command in `src/gpuhunt/__main__.py`.
- (offline providers) The CI workflow in `.github/workflows/catalogs.yml`.
- (online providers) The default catalog in `src/gpuhunt/_internal/default.py`.

### 1.5. Add data quality tests

For offline providers, you can add data quality tests under `src/integrity_tests/`.
Data quality tests are run after collecting offline catalogs to ensure their integrity.

Refer to examples: [test_datacrunch.py](https://github.com/dstackai/gpuhunt/blob/main/src/integrity_tests/test_datacrunch.py),
[test_gcp.py](https://github.com/dstackai/gpuhunt/blob/main/src/integrity_tests/test_gcp.py).

### 1.6. Submit a pull request

Once the cloud provider is added, submit a pull request. 

> Anything unclear? Ask questions on the [Discord server](https://discord.gg/u8SmfwPpMd).

## 2. Integrate the cloud provider to dstackai/dstack

Once the provider is added to `gpuhunt`, we can proceed with implementing 
the corresponding backend with `dstack`. Follow the steps below.

#### 2.1. Determine if you will implement a VM-based or a container-based backend

See the Appendix at the end of this document and make sure the provider meets the outlined requirements.

#### 2.2. Set up the development environment

Follow [DEVELOPMENT.md](DEVELOPMENT.md)`.

#### 2.3. Add dependencies to setup.py

Add any dependencies required by your cloud provider to `setup.py`. Create a separate section with the provider's name for
these dependencies, and ensure that you update the `all` section to include them as well.

#### 2.4. Implement the provider backend

##### 2.4.1. Define the backend type

Add a new enumeration member for your provider to `BackendType` (`src/dstack/_internal/core/models/backends/base.py`).
Use the name of the provider.

Then create a database [migration](MIGRATIONS.md) to reflect the new enum member.

##### 2.4.2. Create the provider directory

Create a new directory under `src/dstack/_internal/core/backends` with the name of the backend type.

##### 2.4.3. Create the backend class

Under the backend directory you've created, create the `__init__.py` file and define the
backend class there (should extend `dstack._internal.core.backends.base.Backend`).

Refer to examples: 
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/datacrunch/__init__.py), 
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/__init__.py), 
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/__init__.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/__init__.py), etc.

##### 2.4.4. Create the backend compute class

Under the backend directory you've created, create the `compute.py` file and define the
backend compute class there (should extend `dstack._internal.core.backends.base.compute.Compute`).

You'll have to implement `get_offers`, `run_job` and `terminate_instance`.
You may need to implement `update_provisioning_data`, see its docstring for details.

For VM-based backends, also implement the `create_instance` method and add the backend name to
[`BACKENDS_WITH_CREATE_INSTANCE_SUPPORT`](`https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/__init__.py`).

Refer to examples:
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/datacrunch/compute.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/compute.py),
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/compute.py),
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/compute.py), etc.

##### 2.4.5. Create the backend config model class

Under the `src/dstack/_internal/core/models/backends` directory, create the file with the name of the backend, and define the
backend config model classes there.

[//]: # (TODO: Mention what config model classes are and how they work)

[//]: # (TODO: Mention what config values class is and how it works)

Refer to examples: 
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/datacrunch.py), 
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/aws.py), 
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/gcp.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/azure.py), etc.

##### 2.4.6. Create the backend config class

Under the backend directory you've created, create the `config.py` file and define the
backend config class there (should extend `dstack._internal.core.backends.base.config.BackendConfig`
and the backend configuration model class defined above).

[//]: # (TODO: Mention what config class is and how it works)

Refer to examples:
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/datacrunch/config.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/config.py), 
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/config.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/config.py), etc.

##### 2.4.7. Import config model classes

Ensure the config model classes are imported
into [`src/dstack/_internal/core/models/backends/__init__.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/__init__.py).

##### 2.4.8. Create the configurator class

Create the file with the backend name under `src/dstack/_internal/server/services/backends/configurators`(https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators)
and define the backend configurator class (must extend `dstack._internal.server.services.backends.configurators.base.Configurator`).

Refer to examples: [datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/datacrunch.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/aws.py), 
[gcp](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/gcp.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/azure.py), etc.

##### 2.4.9. Create the server config class

In [`src/dstack/_internal/server/services/config.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/config.py), 
define the corresponding server config class (that represents the `~/.dstack/server/config.yml` file),
and add it to `AnyBackendConfig` (in the same file).

##### 2.4.10. Add safe imports

In [`src/dstack/_internal/server/services/backends/__init__.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/__init__.py), 
add the `try`/`except` block that imports the backend configurator and appends it to `_CONFIGURATOR_CLASSES`.

##### 2.4.11. (Optional) Override provisioning timeout

If instances in the backend take more than 10 minutes to start, override the default provisioning timeout in
[`src/dstack/_internal/server/background/tasks/common.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/background/tasks/common.py).

## 3. Appendix

#### 3.1. Backend compute type

`dstack` supports two types of backend compute:

- VM-based
- Container-based

#### 3.1.1. VM-based backend compute type

Used if the cloud provider allows provisioning virtual machines (VMs).
When `dstack` provisions a VM, it launches the `dstack-shim` agent inside the VM.
The agent controls the VM and starts Docker containers for users' jobs.

Since `dstack` controls the entire VM, VM-based backends can support more features,
such as blocks, instance volumes, privileged containers, and reusable instances.

To support a VM-based backend, `dstack` expects the following:

- An API for creating and terminating VMs
- An external IP and a public port for SSH
- Cloud-init (preferred)
- VM images with Ubuntu, OpenSSH, GPU drivers, and Docker with NVIDIA runtime

For some VM-based backends, the `dstack` team also maintains
[custom VM images](../scripts/packer/README.md) with the required dependencies
and `dstack`-specific optimizations.

Examples of VM-based backends include: `aws`, `azure`, `gcp`, `lambda`, `datacrunch`, `tensordock`, etc.

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
