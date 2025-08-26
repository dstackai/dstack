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
#image: huggingface/trl-latest-gpu
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

`dstack apply` automatically provisions an instance and sets up an IDE on it.

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
name: vscode

python: "3.11"
ide: vscode

init:
  - pip install wandb
```

</div>

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

The `cpu` property lets you set the architecture (`x86` or `arm`) and core count — e.g., `x86:16` (16 x86 cores), `arm:8..` (at least 8 ARM cores). 
If not set, `dstack` infers it from the GPU or defaults to `x86`.

The `gpu` property lets you specify vendor, model, memory, and count — e.g., `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either), `A100:80GB` (one 80GB A100), `A100:2` (two A100), `24GB..40GB:2` (two GPUs with 24–40GB), `A100:40GB:2` (two 40GB A100s). 

If vendor is omitted, `dstack` infers it from the model or defaults to `nvidia`.

??? info "Google Cloud TPU"
    To use TPUs, specify its architecture via the `gpu` property.

    ```yaml
    type: dev-environment
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

### Docker

#### Default image

If you don't specify `image`, `dstack` uses its base Docker image pre-configured with 
`uv`, `python`, `pip`, essential CUDA drivers, and NCCL tests (under `/opt/nccl-tests/build`). 

Set the `python` property to pre-install a specific version of Python.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: vscode

python: 3.12

ide: vscode
```

</div>

#### NVCC

By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
If you need `nvcc`, set the [`nvcc`](../reference/dstack.yml/dev-environment.md#nvcc) property to true.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: vscode

python: 3.12
nvcc: true

ide: vscode
init:
  - uv pip install flash_attn --no-build-isolation
```

</div>

#### Custom image

If you want, you can specify your own Docker image via `image`.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: vscode    

image: huggingface/trl-latest-gpu

ide: vscode
```

</div>

#### Docker in Docker

Set `docker` to `true` to enable the `docker` CLI in your dev environment, e.g., to run or build Docker images, or use Docker Compose.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: vscode

docker: true

ide: vscode
init:
  - docker run --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi
```

</div>

Cannot be used with `python` or `image`. Not supported on `runpod`, `vastai`, or `kubernetes`.

#### Privileged mode

To enable privileged mode, set [`privileged`](../reference/dstack.yml/dev-environment.md#privileged) to `true`.

Not supported with `runpod`, `vastai`, and `kubernetes`.

#### Private registry
    
Use the [`registry_auth`](../reference/dstack.yml/dev-environment.md#registry_auth) property to provide credentials for a private Docker registry. 

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: vscode

env:
  - NGC_API_KEY

image: nvcr.io/nim/deepseek-ai/deepseek-r1-distill-llama-8b
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}

ide: vscode
```

</div>

### Environment variables

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
name: vscode    

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

### Files

Sometimes, when you run a dev environment, you may want to mount local files. This is possible via the [`files`](../reference/dstack.yml/task.md#_files) property. Each entry maps a local directory or file to a path inside the container.

<div editor-title="examples/.dstack.yml"> 

```yaml
type: dev-environment
name: vscode    

files:
  - .:examples  # Maps the directory where `.dstack.yml` to `/workflow/examples`
  - ~/.ssh/id_rsa:/root/.ssh/id_rsa  # Maps `~/.ssh/id_rsa` to `/root/.ssh/id_rsa`

ide: vscode
```

</div>

If the local path is relative, it’s resolved relative to the configuration file.
If the container path is relative, it’s resolved relative to `/workflow`.

The container path is optional. If not specified, it will be automatically calculated:

<div editor-title="examples/.dstack.yml"> 

```yaml
type: dev-environment
name: vscode    

files:
  - ../examples  # Maps `examples` (the parent directory of `.dstack.yml`) to `/workflow/examples`
  - ~/.ssh/id_rsa  # Maps `~/.ssh/id_rsa` to `/root/.ssh/id_rsa`

ide: vscode
```

</div>

??? info "Upload limit and excludes"
    Whether its a file or folder, each entry is limited to 2MB. To avoid exceeding this limit, make sure to exclude unnecessary files
    by listing it via `.gitignore` or `.dstackignore`.
    The 2MB upload limit can be increased by setting the `DSTACK_SERVER_CODE_UPLOAD_LIMIT` environment variable.

### Repos

Sometimes, you may want to mount an entire Git repo inside the container.

Imagine you have a cloned Git repo containing an `examples` subdirectory with a `.dstack.yml` file:

<div editor-title="examples/.dstack.yml"> 

```yaml
type: dev-environment
name: vscode    

repos:
  # Mounts the parent directory of `examples` (must be a Git repo)
  #   to `/workflow` (the default working directory)
  - ..

ide: vscode
```

</div>

When you run it, `dstack` fetches the repo on the instance, applies your local changes, and mounts it—so the container matches your local repo.

The local path can be either relative to the configuration file or absolute.

??? info "Path"
    Currently, `dstack` always mounts the repo to `/workflow` inside the container. It's the default working directory. 
    Starting with the next release, it will be possible to specify a custom container path.

??? info "Local diff limit and excludes"
    The local diff size is limited to 2MB. To avoid exceeding this limit, exclude unnecessary files
    via `.gitignore` or `.dstackignore`.
    The 2MB local diff limit can be increased by setting the `DSTACK_SERVER_CODE_UPLOAD_LIMIT` environment variable.

??? info "Repo URL"
    Sometimes you may want to mount a Git repo without cloning it locally. In this case, simply provide a URL in `repos`:

    <div editor-title="examples/.dstack.yml"> 

    ```yaml
    type: dev-environment
    name: vscode    

    repos:
      # Clone the specified repo to `/workflow` (the default working directory)
      - https://github.com/dstackai/dstack

    ide: vscode
    ```

    </div>

??? info "Private repos"
    If a Git repo is private, `dstack` will automatically try to use your default Git credentials (from
    `~/.ssh/config` or `~/.config/gh/hosts.yml`).

    If you want to use custom credentials, you can provide them with [`dstack init`](../reference/cli/dstack/init.md).

> Currently, you can configure up to one repo per run configuration.

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
it has been inactive in `dstack ps --verbose` (or `-v`).

<div class="termy">

```shell
$ dstack ps -v
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

### Utilization policy

Sometimes it’s useful to track whether a dev environment is fully utilizing all GPUs. While you can check this with
[`dstack metrics`](../reference/cli/dstack/metrics.md), `dstack` also lets you set a policy to auto-terminate the run if any GPU is underutilized.

Below is an example of a dev environment that auto-terminate if any GPU stays below 10% utilization for 1 hour.

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: my-dev

python: 3.12
ide: cursor

resources:
  gpu: H100:8

utilization_policy:
  min_gpu_utilization: 10
  time_window: 1h
```

</div>

### Schedule

Specify `schedule` to start a dev environment periodically at specific UTC times using the cron syntax:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
ide: vscode
schedule:
  cron: "0 8 * * mon-fri" # at 8:00 UTC from Monday through Friday
```

</div>

The `schedule` property can be combined with `max_duration` or `utilization_policy` to shutdown the dev environment automatically when it's not needed.

??? info "Cron syntax"
    `dstack` supports [POSIX cron syntax](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/crontab.html#tag_20_25_07). One exception is that days of the week are started from Monday instead of Sunday so `0` corresponds to Monday.
    
    The month and day of week fields accept abbreviated English month and weekday names (`jan–dec` and `mon–sun`) respectively.

    A cron expression consists of five fields:

    ```
    ┌───────────── minute (0-59)
    │ ┌───────────── hour (0-23)
    │ │ ┌───────────── day of the month (1-31)
    │ │ │ ┌───────────── month (1-12 or jan-dec)
    │ │ │ │ ┌───────────── day of the week (0-6 or mon-sun)
    │ │ │ │ │
    │ │ │ │ │
    │ │ │ │ │
    * * * * *
    ```

    The following operators can be used in any of the fields:

    | Operator | Description           | Example                                                                 |
    |----------|-----------------------|-------------------------------------------------------------------------|
    | `*`      | Any value             | `0 * * * *` runs every hour at minute 0                                 |
    | `,`      | Value list separator  | `15,45 10 * * *` runs at 10:15 and 10:45 every day.                     |
    | `-`      | Range of values       | `0 1-3 * * *` runs at 1:00, 2:00, and 3:00 every day.                   |
    | `/`      | Step values           | `*/10 8-10 * * *` runs every 10 minutes during the hours 8:00 to 10:59. |

### Spot policy

By default, `dstack` uses on-demand instances. However, you can change that
via the [`spot_policy`](../reference/dstack.yml/dev-environment.md#spot_policy) property. It accepts `spot`, `on-demand`, and `auto`.

--8<-- "docs/concepts/snippets/manage-fleets.ext"

!!! info "Reference"
    Dev environments support many more configuration options,
    incl. [`backends`](../reference/dstack.yml/dev-environment.md#backends), 
    [`regions`](../reference/dstack.yml/dev-environment.md#regions), 
    [`max_price`](../reference/dstack.yml/dev-environment.md#max_price), and
    [`max_duration`](../reference/dstack.yml/dev-environment.md#max_duration), 
    among [others](../reference/dstack.yml/dev-environment.md).


--8<-- "docs/concepts/snippets/manage-runs.ext"

!!! info "What's next?"
    1. Read about [tasks](tasks.md) and [services](services.md)
    2. Learn how to manage [fleets](fleets.md)
