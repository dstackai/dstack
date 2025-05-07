# Dev environments

A dev environment lets you provision an instance and access it with your desktop IDE.

## Apply a configuration

First, define a dev environment configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title="examples/.dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode

python: "3.11"
# Uncomment to use a custom Docker image
#image: dstackai/base:py3.13-0.7-cuda-12.1
ide: vscode

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  gpu: 24GB
```

</div>

To run a dev environment, pass the configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f examples/.dstack.yml

 #  BACKEND  REGION    RESOURCES                SPOT  PRICE
 1  runpod   CA-MTL-1  9xCPU, 48GB, A5000:24GB  yes   $0.11
 2  runpod   EU-SE-1   9xCPU, 43GB, A5000:24GB  yes   $0.11
 3  gcp      us-west4  4xCPU, 16GB, L4:24GB     yes   $0.214516

Submit the run vscode? [y/n]: y

Launching `vscode`...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+vscode/workflow
```

</div>

`dstack apply` automatically provisions an instance, uploads the contents of the repo (incl. your local uncommitted changes),
and sets up an IDE on the instance.

??? info "Windows"
    On Windows, `dstack` works both natively and inside WSL. But, for dev environments, 
    it's recommended _not to use_ `dstack apply` _inside WSL_ due to a [VS Code issue :material-arrow-top-right-thin:{ .external }](https://github.com/microsoft/vscode-remote-release/issues/937){:target="_blank"}.

To open the dev environment in your desktop IDE, use the link from the output 
(such as `vscode://vscode-remote/ssh-remote+fast-moth-1/workflow`).

![](../../assets/images/dstack-vscode-jupyter.png){ width=800 }

??? info "SSH"

    Alternatively, while the CLI is attached to the run, you can connect to the dev environment via SSH:
    
    <div class="termy">
    
    ```shell
    $ ssh vscode
    ```
    
    </div>

## Configuration options

### Initialization

If you want to pre-configure the dev environment, specify the [`init`](../reference/dstack.yml/dev-environment.md#init)
property with a list of commands to run at startup:

<div editor-title="examples/.dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode

python: "3.11"
ide: vscode

# Commands to run on startup
init:
  - pip install wandb
```

</div>

### Inactivity duration

Set [`inactivity_duration`](../reference/dstack.yml/dev-environment.md#inactivity_duration)
to automatically stop the dev environment after a configured period of inactivity.

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: vscode
ide: vscode

# Stop if inactive for 2 hours
inactivity_duration: 2h
```

</div>

The dev environment becomes inactive when you close the remote VS Code window,
close any `ssh <run name>` shells, and stop the `dstack apply` or `dstack attach` command.
If you go offline without stopping anything manually, the dev environment will also become inactive
within about 3 minutes.

If `inactivity_duration` is configured for your dev environment, you can see how long
it has been inactive in `dstack ps --verbose`.

<div class="termy">

```shell
$ dstack ps --verbose
 NAME    BACKEND  RESOURCES       PRICE    STATUS                 SUBMITTED
 vscode  cudo     2xCPU, 8GB,     $0.0286  running                8 mins ago
                  100.0GB (disk)           (inactive for 2m 34s)
```

</div>

If you reattach to the dev environment using [`dstack attach`](../reference/cli/dstack/attach.md),
the inactivity timer will be reset within a few seconds.

??? info "In-place update"
    As long as the configuration defines the `name` property, the value of `inactivity_duration`
    can be changed for a running dev environment without a restart.
    Just change the value in the configuration and run `dstack apply` again.

    <div class="termy">

    ```shell
    $ dstack apply -f .dstack.yml

    Detected configuration changes that can be updated in-place: ['inactivity_duration']
    Update the run? [y/n]:
    ```

    </div>

> `inactivity_duration` is not to be confused with [`idle_duration`](#idle-duration).
> The latter determines how soon the underlying cloud instance will be terminated
> _after_ the dev environment is stopped.

### Resources

When you specify a resource value like `cpu` or `memory`,
you can either use an exact value (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

resources:
  # 16 or more x86_64 cores
  cpu: 16..
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

The `cpu` property also allows you to specify the CPU architecture, `x86` or `arm`. Examples:
`x86:16` (16 x86-64 cores), `arm:8..` (at least 8 ARM64 cores).
If the architecture is not specified, `dstack` tries to infer it from the `gpu` specification
using `x86` as the fallback value.

The `gpu` property allows specifying not only memory size but also GPU vendor, names
and their quantity. Examples: `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either A10G or A100),
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB),
`A100:40GB:2` (two A100 GPUs of 40GB).
If the vendor is not specified, `dstack` tries to infer it from the GPU name using `nvidia` as the fallback value.

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

> If you’re unsure which offers (hardware configurations) are available from the configured backends, use the
> [`dstack offer`](../reference/cli/dstack/offer.md#list-gpu-offers) command to list them.

### Python version

If you don't specify `image`, `dstack` uses its base Docker image pre-configured with 
`python`, `pip`, `conda` (Miniforge), and essential CUDA drivers. 
The `python` property determines which default Docker image is used.

??? info "nvcc"
    By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
    If you need `nvcc`, set the [`nvcc`](../reference/dstack.yml/dev-environment.md#nvcc) property to true.

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

!!! info "Privileged mode"
    To enable privileged mode, set [`privileged`](../reference/dstack.yml/dev-environment.md#privileged) to `true`.
    This mode allows using [Docker and Docker Compose](../guides/protips.md#docker-and-docker-compose) inside `dstack` runs.

    Not supported with `runpod`, `vastai`, and `kubernetes`.

??? info "Private registry"
    Use the [`registry_auth`](../reference/dstack.yml/dev-environment.md#registry_auth) property to provide credentials for a private Docker registry. 

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

If you don't assign a value to an environment variable (see `HF_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

??? info "System environment variables"
    The following environment variables are available in any run by default:
    
    | Name                    | Description                             |
    |-------------------------|-----------------------------------------|
    | `DSTACK_RUN_NAME`       | The name of the run                     |
    | `DSTACK_REPO_ID`        | The ID of the repo                      |
    | `DSTACK_GPUS_NUM`       | The total number of GPUs in the run     |

### Spot policy

By default, `dstack` uses on-demand instances. However, you can change that
via the [`spot_policy`](../reference/dstack.yml/dev-environment.md#spot_policy) property. It accepts `spot`, `on-demand`, and `auto`.

!!! info "Reference"
    Dev environments support many more configuration options,
    incl. [`backends`](../reference/dstack.yml/dev-environment.md#backends), 
    [`regions`](../reference/dstack.yml/dev-environment.md#regions), 
    [`max_price`](../reference/dstack.yml/dev-environment.md#max_price), and
    [`max_duration`](../reference/dstack.yml/dev-environment.md#max_duration), 
    among [others](../reference/dstack.yml/dev-environment.md).

### Retry policy

By default, if `dstack` can't find capacity or the instance is interrupted, the run will fail.

If you'd like `dstack` to automatically retry, configure the 
[retry](../reference/dstack.yml/dev-environment.md#retry) property accordingly:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode    

ide: vscode

retry:
  # Retry on specific events
  on_events: [no-capacity, error, interruption]
  # Retry for up to 1 hour
  duration: 1h
```

</div>

--8<-- "docs/concepts/snippets/manage-fleets.ext"

--8<-- "docs/concepts/snippets/manage-runs.ext"

!!! info "What's next?"
    1. Read about [tasks](tasks.md), [services](services.md), and [repos](repos.md)
    2. Learn how to manage [fleets](fleets.md)
