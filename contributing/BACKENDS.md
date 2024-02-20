# How to add a new backend

## Overview

1. Add cloud provider to `gpuhunt`
    1. Add `src/gpuhunt/providers/<name>.py`
    2. Define class attribute `NAME` and implement
2. Add Backend, Compute, and configuration models in `dstack`

## dstackai/gpuhunt

Clone and open https://github.com/dstackai/gpuhunt. Create `<YourName>Provider` class
in `src/gpuhunt/providers/<yourprovider>.py`.

Your class must inherit `AbstractProvider`, have `NAME` class variable, and implement `get` method. Use
optional `query_filter` to speed up the query. Use `balance_resources` if your backend provides fine-grained control on
resources like RAM and CPU to prevent under-optimal configurations (i.e., A100 80GB with 1 GB of RAM).

`get` method is called during catalog generation for `offline` providers and every query for `online` providers.

> There are two types of providers in `gpuhunt`:
>1. `offline` — providers that take a lot of time to get all offers. A catalog is precomputed and stored as csv file
>2. `online` — providers that take a few seconds to get all offers. A catalog is computed in a real-time as needed

If your provider is `offline`, also add data quality tests to `src/integrity_tests/test_<yourprovider>.py` to verify
generated csv files before publication.

## dstackai/dstack

Clone and open https://github.com/dstackai/dstack. Follow `CONTRIBUTING.md` to setup your environment.

Add your dependencies to `setup.py` in a separate `<yourprovider>` section. Also, update `all` section.

Add a new enum entry `BackendType.<YourBackend>` at `src/dstack/_internal/core/models/backends/base.py`.

Create `src/dstack/_internal/core/backends/<yourprovider>` directory:

- Implement `YourProviderBackend` in `__init__.py`, inherit it from `BaseBackend`.
    - Define the `TYPE` class variable.
- Implement `<YourProvider>Compute` in `compute.py`, and inherit it from `Compute`.
    - Implement `get_offers`. It will be called every time the user wants to provision something. Add availability
      information if possible.
    - Implement `run_job`. Here you create a compute resource and run `dstack-shim` or `dstack-runner`.
    - Implement `terminate_instance`. This method should not raise an error, if there is no such instance.
- Implement `<YourProvider>Config` in `config.py`, inherit it from `BackendConfig` and `<YourProvider>StoredConfig`.
  This config is accepted by `<YourProvider>Backend` class.

> There are two types of compute in `dstask`:
>1. `dockerized: False` — the backend runs `dstack-shim`. Later, `dstack-shim` will create a job container
    with `dstack-runner` in it. This is common for VM.
>2. `dockerized: True` — the backend runs `dstack-runner` inside a docker container.

> Note, that the Compute class interface is subject to changes with the coming pools feature release.

Create configuration models in `src/dstack/_internal/core/models/backends/<yourprovider>.py`. `<YourProvider>ConfigInfo`
contains everything except for the credentials. You may have multiple models for credentials (i.e., default
credentials & explicit credentials). Create a model with creds: `<YourProvider>ConfigInfoWithCreds`. Create a model with
all fields being optional: `<YourProvider>ConfigInfoWithCredsPartial`. Create a model representing UI elements for
configurator: `<YourProvider>ConfigValues`.

Import all created models to `src/dstack/_internal/core/models/backends/__init__.py`.

Implement `<YourProvider>Configurator`
in `src/dstack/_internal/server/services/backends/configurators/<yourprovider>.py`

Add `<YourProvider>Config` in `src/dstack/_internal/server/services/config.py`. This model represents the YAML
configuration.

Add safe import for your backend in `src/dstack/_internal/server/services/backends/__init__.py`. Update expected
backends in tests in `src/tests/_internal/server/routers/test_backends.py`.

## Appendix

### Adding VM compute backend

`dstack` expects the following features from your backend:

- Ubuntu 22.04 LTS
- Nvidia Drivers 535
- Docker with Nvidia runtime
- OpenSSH server
- External IP & 1 port for SSH (any)
- cloud-init script (preferable)
- API for creating and terminating instances

To accelerate provisioning — we prebuild VM images with necessary dependencies. You can find configurations
in `packer/`.

### Adding Docker-only compute backend

`dstack` expects the following features from your backend:

- Docker with Nvidia runtime
- External IP & 1 port for SSH (any)
- Container entrypoint override (~2KB)
- API for creating and terminating containers