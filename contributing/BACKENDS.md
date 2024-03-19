# How to add a new backend to dstack

The guide below explains the steps required to extend `dstack` with support for a new cloud provider.

## Overview of the process

1. Add the cloud provider to [gpuhunt](https://https://github.com/dstackai/gpuhunt)
2. Integrate the cloud provider into [dstack](https://https://github.com/dstackai/dstack)

## 1. Add a cloud provider to dstackai/gpuhunt

The [gpuhunt](https://https://github.com/dstackai/gpuhunt) project is a utility that `dstack` uses to collect information
about cloud providers, their supported machine configurations, pricing, etc. This information is later used by `dstack`
for provisioning machines.

Thus, in order to support a new cloud provider with `dstack`, you first need to add the cloud provider to `gpuhunt`.

To add a new cloud provider to `gpuhunt`, follow these steps:

### 1.1. Clone the repo

```bash
git clone https://github.com/dstackai/gpuhunt.git
```

### 1.2. Create the provider class

Create the provider class file under `src/gpuhunt/providers`. 

Ensure your class...

- Extends the `AbstractProvider` base class.
- Has the `NAME` property, that will be used as the unique identifier for your provider.
- Implements the `get` method, that is responsible for fetching the available machine configurations from the cloud provider.

[//]: # (TODO: Ellaborate better on how to use `query_filter` and `balance_resources`)

Refer to examples: [datacrunch.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/datacrunch.py), 
[aws.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/aws.py), 
[gcp.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/gcp.py), 
[azure.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/azure.py), 
[lambdalabs.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/lambdalabs.py), 
[tensordock.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/tensordock.py), 
[vastai.py](https://github.com/dstackai/gpuhunt/blob/main/src/gpuhunt/providers/vastai.py). 

### 1.3. Register the provider with the catalog

Update the `src/gpuhunt/_internal/catalog.py` file by adding the provider name
to either `OFFLINE_PROVIDERS` or `ONLINE_PROVIDERS` depending on the type of the provider.

How do I decide which type my provider is?

- `OFFLINE_PROVIDERS` - Use this type if your provider offers static machine configurations that may be collected and
  published on a daily basis. Examples: `aws`, `gcp`, `azure`, etc. These providers offer many machine configurations,
  but they are not updated frequently.
- `ONLINE_PROVIDERS` - Use this type if your provider offers dynamic machine configurations that are available at the very moment when you fetch configurations (e.g., GPU marketplaces).
   Examples: `tensordock`, `vast`, etc.

### 1.4. Add data quality tests

If the provider is registered via `OFFLINE_PROVIDERS`, you can add data quality tests 
under `src/integrity_tests/`.

Refer to examples: [test_datacrunch.py](https://github.com/dstackai/gpuhunt/blob/main/src/integrity_tests/test_datacrunch.py),
[test_gcp.py](https://github.com/dstackai/gpuhunt/blob/main/src/integrity_tests/test_gcp.py).

> Anything unclear? Ask questions on the [Discord server](https://discord.gg/u8SmfwPpMd).

Once the cloud provider is added, submit a pull request. 


## 2. Integrate the cloud provider to dstackai/dstack

Once the provider is added to `gpuhunt`, we can proceed with implementing 
the corresponding backend with `dstack`. Follow the steps below.

#### 2.1 Clone the repo

```bash
git clone https://github.com/dstackai/dstack.git
```

#### 2.2. Set up the development environment

Follow [DEVELOPMENT.md](DEVELOPMENT.md)`.

#### 2.3. Add dependencies to setup.py

Add any dependencies required by your cloud provider to `setup.py`. Create a separate section with the provider's name for
these dependencies, and ensure that you update the `all` section to include them as well.

#### 2.4. Implement the provider backend

##### 2.4.1. Define the backend type

Add a new enumeration member for your provider to `BackendType` (`src/dstack/_internal/core/models/backends/base.py`).
Use the name of the provider.

##### 2.4.2. Create the provider directory

Create a new directory under `src/dstack/_internal/core/backends` with the name of the backend type.

##### 2.4.3. Create the backend class

Under the backend directory you've created, create the `__init__.py` file and define the
backend class there (should extend `dstack._internal.core.backends.base.Backend`).

Refer to examples: 
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/datacrunch/__init__.py), 
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/__init__.py), 
[gcp.py](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/__init__.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/__init__.py), etc.

##### 2.4.4. Create the backend compute class

Under the backend directory you've created, create the `compute.py` file and define the
backend compute class there (should extend `dstack._internal.core.backends.base.compute.Compute`).

You'll have to implement `get_offers`, `create_instance`, `run_job` and `terminate_instance`.

The `create_instance` method is required for the pool feature. If you implement the `create_instance` method, you should add the provider name to `BACKENDS_WITH_CREATE_INSTANCE_SUPPORT`. (`src/dstack/_internal/server/services/runs.py`).

Refer to examples:
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/datacrunch/compute.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/compute.py),
[gcp.py](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/compute.py),
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/compute.py), etc.

##### 2.4.5. Create the backend config model class

Under the `src/dstack/_internal/core/models/backends` directory, create the file with the name of the backend, and define the
backend config model classes there.

[//]: # (TODO: Mention what config model classes are and how they work)

[//]: # (TODO: Mention what config values class is and how it works)

Refer to examples: 
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/datacrunch.py), 
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/aws.py), 
[gcp.py](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/gcp.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/azure.py), etc.

##### 2.4.6. Create the backend config class

Under the backend directory you've created, create the `config.py` file and define the
backend config class there (should extend `dstack._internal.core.backends.base.config.BackendConfig`
and the backend configuration model class defined above).

[//]: # (TODO: Mention what config class is and how it works)

Refer to examples:
[datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/datacrunch/config.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/aws/config.py), 
[gcp.py](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/gcp/config.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/backends/azure/config.py), etc.

##### 2.4.7. Import config model classes

Ensure the config model classes are imported
into [`src/dstack/_internal/core/models/backends/__init__.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/core/models/backends/__init__.py).

[//]: # (TODO: The backend configuration is overly complex and needs simplification: https://github.com/dstackai/dstack/issues/888)

##### 2.4.8. Create the configurator class

Create the file with the backend name under `src/dstack/_internal/server/services/backends/configurators`(https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators)
and define the backend configurator class (must extend `dstack._internal.server.services.backends.configurators.base.Configurator`).

Refer to examples: [datacrunch](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/datacrunch.py),
[aws](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/aws.py), 
[gcp.py](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/gcp.py), 
[azure](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/configurators/azure.py), etc.

##### 2.4.9. Create the server config class

In [`src/dstack/_internal/server/services/config.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/config.py), 
define the corresponding server config class (that represents the `~/.dstack/server/config.yml` file),
and add it to `AnyBackendConfig` (in the same file).

##### 2.4.10. Add safe imports

In [`src/dstack/_internal/server/services/backends/__init__.py`](https://github.com/dstackai/dstack/blob/master/src/dstack/_internal/server/services/backends/__init__.py), 
add the `try`/`except` block that imports the backend configurator and appends it to `_CONFIGURATOR_CLASSES`.

## 3. Appendix

#### 3.1. Backend compute type

`dstack` supports two types of backend compute:

- VM-based
- Container-based

#### 3.1.1. VM-based backend compute type

It's when the cloud provider allows provisioning Virtual machines (VMs). 
This is the most flexible backend compute type.

[//]: # (TODO: Elaborate why it's the most flexible)

To support it, `dstack` expects the following from the cloud provider:

- An API for creating and terminating VMs
- Ubuntu 22.04 LTS
- NVIDIA CUDA driver 535
- Docker with NVIDIA runtime
- OpenSSH server
- Cloud-init script (preferred)
- An external IP and public port for SSH

When `dstack` provisions a VM, it launches there `dstack-shim`.

[//]: # (TODO: Ellaborate on what dstach-shim is and how it works)

The examples of VM-based backends include: `aws`, `azure`, `gcp`, `lambda`, `datacrunch`, `tensordock`, etc.

[//]: # (TODO: Elaborate on packer scripts)

#### 3.1.2. Container-based backend compute type

It's when the cloud provider allows provisioning only containers.
This is the most limited backend compute type. 

[//]: # (TODO: Elaborate on why it's the most limited)

To support it, `dstack` expects the following from the cloud provider:

- An API for creating and terminating containers
- Docker with NVIDIA runtime
- An external IP and a public port for SSH
- A way to override the container entrypoint (at least ~2KB)

The examples of VM-based backends include: `kubernetes`, `vastai`, etc.

Note: There are two types of compute in dstack:

When `dstack` provisions a VM, it launches there `dstack-runner`.

[//]: # (TODO: Ellaborate on what dstach-runner is and how it works)

[//]: # (TODO: Update this guide to incorporate the pool feature)