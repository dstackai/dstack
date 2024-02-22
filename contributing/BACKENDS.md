# How to add a Backend to dstack.ai
## Introduction

Welcome to the Integration Guide for adding a backend by intergrating new cloud providers to gpuhunt and extending the capabilities of dstack.<br> 
This document is designed to assist developers and contributors in integrating additional cloud computing resources into dstack.


## Overview of Steps

1. Add cloud provider to `gpuhunt`
2. Integrating a Cloud Provider into dstackai/dstack

## Adding a cloud provider to dstackai/gpuhunt
To integrate a new cloud provider into `gpuhunt`, follow these steps:

1. **Clone the Repository**: Start by cloning the `gpuhunt` repository from GitHub:
```bash
https://github.com/dstackai/gpuhunt.git
```
 2. **Create the Provider Class**: Navigate to the `providers` directory and create a new Python file for your provider:
- Path: `src/gpuhunt/providers/<YourProvider>.py`
- Replace `<YourProvider>` with the name of your cloud provider.

3. **Implement the Provider Class**: Your class should meet the following criteria:

- **Inherit from `AbstractProvider`**: Ensure your class extends the `AbstractProvider` base class.
  ```python
  from gpuhunt.providers import AbstractProvider

  class <YourName>Provider(AbstractProvider):
  ```

- **Define the `NAME` Class Variable**: This should be a unique identifier for your provider.

  ```python
  NAME = '<YourProvider>_name'
  ```

- **Implement the `get` Method**: This method is responsible for fetching the available GPU resources information from your cloud provider. Implement it according to the `AbstractProvider` interface.

  ```python
  def get(self, query_filter: Optional[QueryFilter] = None, balance_resources: bool = True) -> List[RawCatalogItem]:
      # Implementation here
  ```
- **Utilize `query_filter`**: (Optional) Use this parameter to speed up the query process by filtering results early on.

- **Use `balance_resources`**: If your backend offers detailed control over resources (like RAM and CPU), to prevent configurations that are not optimal, such as pairing a high-end GPU with insufficient RAM (i.e., A100 80GB with 1 GB of RAM).

4. **Understand Provider Types**:
- `gpuhunt` distinguishes between two types of providers:
  1. **`offline`**: These providers take a significant amount of time to retrieve all offers. A catalog is precomputed and stored as a CSV file.
  2. **`online`**: These providers can fetch all offers within a few seconds. A catalog is computed in real-time as needed.


5. **Data Quality Tests for Offline Providers**:
- If your provider is classified as `offline`, you should add data quality tests to ensure the integrity of the precomputed CSV files. These tests are located in:
  ```
  src/integrity_tests/test_<YourProvider>.py
  ```
- Replace `<YourProvider>` with the name of your cloud provider. These tests verify the generated CSV files before publication to ensure accuracy and reliability.


## Integrating a Cloud Provider into dstackai/dstack

Integrating a new cloud provider into `dstack` involves several key steps, from setting up your development environment to implementing specific backend configurations. Here’s how to proceed:

### Setup and Initial Configuration

1. **Clone the `dstack` Repository**: Begin by cloning the `dstack` repository from GitHub:

```bash
git clone https://github.com/dstackai/dstack.git
```

2. **Follow Setup Instructions**: Consult the `CONTRIBUTING.md` document within the repository for instructions on setting up your development environment.

### Modifying `setup.py`

1. **Add Dependencies**: Incorporate any dependencies required by your cloud provider into `setup.py`. Create a separate section named `<YourProvider>` for these dependencies and ensure to update the `all` section to include them.

### Extending Backend Models

1. **Add Backend Type**: Insert a new enumeration entry for your backend in `src/dstack/_internal/core/models/backends/base.py`:

```python
<YOURBACKEND> = '<your_backend>'
```
2. **Create Provider Directory**: Establish a new directory at `src/dstack/_internal/core/backends/<YourProvider> `to house your provider’s backend and compute implementations.


3. **Backend Implementation:** 
In `__init__.py`, implement `<YourProvider>Backend`, inheriting from `BaseBackend`. Define the `TYPE` class variable to associate your backend with the newly added enum entry.

4. **Compute Implementation:** 
In `compute.py`, develop `<YourProvider>Compute`, inheriting from `Compute`.<br> 

You'll need to implement methods like      
  - `get_offers` It will be called every time the user wants to provision something. Add availability information if possible. 
  - `run_job` Here you create a compute resource and run `dstack-shim` or `dstack-runner`.
  - `terminate_instance` This method should not raise an error, if there is no such instance.

5. **Configuration Implementation**:
- Implement the `<YourProvider>Config` class in `config.py`, inheriting from both `BackendConfig` and `<YourProvider>StoredConfig`. This configuration is accepted by the `<YourProvider>Backend` class.


### Configuration Models
 1. **Create Configuration Models:**

You may have multiple models for credentials (i.e., default credentials & explicit credentials). 
 In `src/dstack/_internal/core/models/backends/<YourProvider>.py`, create models for your provider's configuration:
- `<YourProvider>ConfigInfo:` create a model with all configuration details except credentials.
- `<YourProvider>ConfigInfoWithCreds`: create a model with credentials.
- `<YourProvider>ConfigInfoWithCredsPartial`: create a model with all fields optional.
- `<YourProvider>ConfigValues:` create a model representing UI elements for configurator.

2. **Import Models:**
Ensure all new models are imported into `src/dstack/_internal/core/models/backends/__init__.py`.

### Finalizing Integration
1. **Implement Configurator:**
Develop `<YourProvider>Configurator` in `src/dstack/_internal/server/services/backends/configurators/<YourProvider>.py`.

2. **Add YAML Configuration Model:**
Insert `<YourProvider>Config` in `src/dstack/_internal/server/services/config.py` to represent the provider’s configuration in YAML.

3. **Ensure Safe Import:** 
Add a safe import for your backend in `src/dstack/_internal/server/services/backends/__init__.py` and update expected backends in tests within `src/tests/_internal/server/routers/test_backends.py.`





## Appendix
### Adding VM Compute Backend
dstack expects VM backends to have:

- Ubuntu 22.04 LTS
- Nvidia Drivers 535
- Docker with Nvidia runtime
- OpenSSH server
- External IP & 1 port for SSH (any)
- cloud-init script (preferred)
- API for creating and terminating instances

To speed up provisioning, we prebuild VM images with necessary dependencies, available in `packer/`.

Examples: `aws`, `azure`, `gcp` etc

### Adding Docker-only Compute Backend
For Docker-only backends, dstack requires:

- Docker with Nvidia runtime
- External IP & 1 port for SSH (any)
- Container entrypoint override (~2KB)
- API for creating and terminating containers

Examples: `kubernetes`, `vastai` etc

Note: There are two types of compute in dstack:

- `dockerized: False` — the backend runs `dstack-shim`. This setup is common for VMs.
- `dockerized: True`— the backend directly runs `dstack-runner` inside a docker container.

The Compute class interface may undergo changes with the upcoming pools feature release, so keep an eye out for updates.

