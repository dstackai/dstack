# dev-environment

The `dev-environment` configuration type allows running [dev environments](../../dev-environments.md).

> Configuration files must be inside the project repo, and their names must end with `.dstack.yml` 
> (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).
> Any configuration can be run via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

### Python version

If you don't specify `image`, `dstack` uses its base Docker image pre-configured with 
`python`, `pip`, `conda` (Miniforge), and essential CUDA drivers. 
The `python` property determines which default Docker image is used.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

# If `image` is not specified, dstack uses its base image
python: "3.10"

ide: vscode
```

</div>

??? info "nvcc"
    By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
    If you need `nvcc`, set the corresponding property to true.

    ```yaml
    type: dev-environment
    # The name is optional, if not specified, generated randomly
    name: vscode    
    
    # If `image` is not specified, dstack uses its base image
    python: "3.10"
    # Ensure nvcc is installed (req. for Flash Attention) 
    nvcc: true

    ide: vscode
    ```

### Docker

If you want, you can specify your own Docker image via `image`.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

# Any custom Docker image
image: ghcr.io/huggingface/text-generation-inference:latest

ide: vscode
```

</div>

??? info "Private registry"

    Use the `registry_auth` property to provide credentials for a private Docker registry. 

    ```yaml
    type: dev-environment
    # The name is optional, if not specified, generated randomly
    name: vscode    

    # Any private Docker image
    image: ghcr.io/huggingface/text-generation-inference:latest
    # Credentials of the private Docker registry
    registry_auth:
      username: peterschmidt85
      password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5
    
    ide: vscode
    ```

!!! info "Docker and Docker Compose"
    All backends except `runpod`, `vastai` and `kubernetes` also allow to use [Docker and Docker Compose](../../guides/protips.md#docker-and-docker-compose) 
    inside `dstack` runs.

### Resources { #_resources }

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

resources:
  # 200GB or more RAM
  memory: 200GB..
  # 4 GPUs from 40GB to 80GB
  gpu: 40GB..80GB:4
  # Shared memory (required by multi-gpu)
  shm_size: 16GB
  # Disk size
  disk: 500GB
```

</div>

The `gpu` property allows specifying not only memory size but also GPU vendor, names
and their quantity. Examples: `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either A10G or A100),
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB),
`A100:40GB:2` (two A100 GPUs of 40GB).

??? info "Google Cloud TPU"
    To use TPUs, specify its architecture via the `gpu` property.

    ```yaml
    type: dev-environment
    # The name is optional, if not specified, generated randomly
    name: vscode    
    
    ide: vscode
    
    resources:
      gpu: v2-8
    ```

    Currently, only 8 TPU cores can be specified, supporting single TPU device workloads. Multi-TPU support is coming soon.

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

### Environment variables

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

# Environment variables
env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1

ide: vscode
```

</div>

> If you don't assign a value to an environment variable (see `HF_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.envrc` file and utilize tools like `direnv`.

#### System environment variables

The following environment variables are available in any run and are passed by `dstack` by default:

| Name                    | Description                             |
|-------------------------|-----------------------------------------|
| `DSTACK_RUN_NAME`       | The name of the run                     |
| `DSTACK_REPO_ID`        | The ID of the repo                      |
| `DSTACK_GPUS_NUM`       | The total number of GPUs in the run     |

### Spot policy

You can choose whether to use spot instances, on-demand instances, or any available type.

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

# Uncomment to leverage spot instances
#spot_policy: auto
```

</div>

The `spot_policy` accepts `spot`, `on-demand`, and `auto`. The default for dev environments is `on-demand`.

### Backends

By default, `dstack` provisions instances in all configured backends. However, you can specify the list of backends:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

# Use only listed backends
backends: [aws, gcp]
```

</div>

### Regions

By default, `dstack` uses all configured regions. However, you can specify the list of regions:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

# Use only listed regions
regions: [eu-west-1, eu-west-2]
```

</div>

### Volumes

Volumes allow you to persist data between runs.
To attach a volume, simply specify its name using the `volumes` property and specify where to mount its contents:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

# Map the name of the volume to any path
volumes:
  - name: my-new-volume
    path: /volume_data
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the dev
environment, and its contents will persist across runs.

??? Info "Instance volumes"
    If data persistence is not a strict requirement, use can also use
    ephemeral [instance volumes](../../concepts/volumes.md#instance-volumes).

!!! info "Limitations"
    When you're running a dev environment, task, or service with `dstack`, it automatically mounts the project folder contents
    to `/workflow` (and sets that as the current working directory). Right now, `dstack` doesn't allow you to 
    attach volumes to `/workflow` or any of its subdirectories.

The `dev-environment` configuration type supports many other options. See below.

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.DevEnvironmentConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

## `resources.gpu` { #resources-gpu data-toc-label="resources.gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `resources.disk` { #resources-disk data-toc-label="resources.disk" }

#SCHEMA# dstack._internal.core.models.resources.DiskSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `registry_auth`

#SCHEMA# dstack._internal.core.models.configurations.RegistryAuth
    overrides:
      show_root_heading: false
      type:
        required: true

## `volumes[n]` { #_volumes data-toc-label="volumes" }

=== "Network volumes"

    #SCHEMA# dstack._internal.core.models.volumes.VolumeMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

=== "Instance volumes"

    #SCHEMA# dstack._internal.core.models.volumes.InstanceMountPoint
        overrides:
          show_root_heading: false
          type:
            required: true

??? info "Short syntax"

    The short syntax for volumes is a colon-separated string in the form of `source:destination`

    * `volume-name:/container/path` for network volumes
    * `/instance/path:/container/path` for instance volumes
