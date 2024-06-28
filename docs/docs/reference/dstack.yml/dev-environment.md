# dev-environment

The `dev-environment` configuration type allows running [dev environments](../../concepts/dev-environments.md).

> Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `serve.dstack.yml` are both acceptable)
> and can be located in the project's root directory or any nested folder.
> Any configuration can be run via [`dstack run`](../cli/index.md#dstack-run).

## Examples

### Python version

If you don't specify `image`, `dstack` uses the default Docker image pre-configured with 
`python`, `pip`, `conda` (Miniforge), and essential CUDA drivers. 
The `python` property determines which default Docker image is used.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

python: "3.11"

ide: vscode
```

</div>

!!! info "nvcc"
    Note that the default Docker image doesn't bundle `nvcc`, which is required for building custom CUDA kernels. 
    To install it, use `conda install cuda`.

### Docker image

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

image: ghcr.io/huggingface/text-generation-inference:latest

ide: vscode
```

</div>

??? info "Private registry"

    Use the `registry_auth` property to provide credentials for a private Docker registry. 

    ```yaml
    type: dev-environment
    
    image: ghcr.io/huggingface/text-generation-inference:latest
    registry_auth:
      username: peterschmidt85
      password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5
    
    ide: vscode
    ```

### Resources { #_resources }

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

ide: vscode

resources:
  # 200GB or more RAM
  memory: 200GB..

  # 4 GPUs from 40GB to 80GB
  gpu: 40GB..80GB:4

  # Shared memory
  shm_size: 16GB

  disk: 500GB
```

</div>

The `gpu` property allows specifying not only memory size but also GPU names
and their quantity. Examples: `A100` (one A100), `A10G,A100` (either A10G or A100), 
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB), 
`A100:40GB:2` (two A100 GPUs of 40GB).

??? info "Google Cloud TPU"
    To use TPUs, specify its architecture prefixed by `tpu-` via the `gpu` property.

    ```yaml
    type: dev-environment
    
    ide: vscode
    
    resources:
      gpu:  tpu-v2-8
    ```

    Currently, only 8 TPU cores can be specified, supporting single TPU device workloads. Multi-TPU support is coming soon.

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

### Environment variables

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

env:
  - HUGGING_FACE_HUB_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1

ide: vscode
```

</div>

If you don't assign a value to an environment variable (see `HUGGING_FACE_HUB_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.env` file and utilize tools like `direnv`.

#### Default environment variables

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

ide: vscode

spot_policy: auto
```

</div>

The `spot_policy` accepts `spot`, `on-demand`, and `auto`. The default for dev environments is `on-demand`.

### Backends

By default, `dstack` provisions instances in all configured backends. However, you can specify the list of backends:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment

ide: vscode

backends: [aws, gcp]
```

</div>

### Regions

By default, `dstack` uses all configured regions. However, you can specify the list of regions:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment

ide: vscode

regions: [eu-west-1, eu-west-2]
```

</div>

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

## `volumes`

#SCHEMA# dstack._internal.core.models.volumes.VolumeMountPoint
    overrides:
      show_root_heading: false
      type:
        required: true
