# Tasks

A task allows you to run arbitrary commands on one or more nodes.
They are best suited for jobs like training or batch processing.

## Apply a configuration

First, define a task configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

[//]: # (TODO: Make tabs - single machine & distributed tasks & web app)

<div editor-title=".dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: trl-sft    

python: 3.12

# Uncomment to use a custom Docker image
#image: huggingface/trl-latest-gpu

env:
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  # One to two H100 GPUs
  gpu: H100:1..2
  shm_size: 24GB
```

</div>

To run a task, pass the configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f .dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:3  yes   $0.33

Submit the run trl-sft? [y/n]: y

Launching `axolotl-train`...
---> 100%

{'loss': 1.4967, 'grad_norm': 1.2734375, 'learning_rate': 1.0000000000000002e-06, 'epoch': 0.0}
  0% 1/24680 [00:13<95:34:17, 13.94s/it]
  6% 73/1300 [00:48<13:57,  1.47it/s]
```

</div>

`dstack apply` automatically provisions instances and runs the task.

## Configuration options

### Ports

A task can configure ports. In this case, if the task is running an application on a port, `dstack apply` 
will securely allow you to access this port from your local machine through port forwarding.

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: streamlit-hello

python: 3.12

commands:
  - uv pip install streamlit
  - streamlit hello
ports: 
  - 8501
```

</div>

When running it, `dstack apply` forwards `8501` port to `localhost:8501`, enabling secure access to the running
application.

### Distributed tasks

By default, a task runs on a single node.
However, you can run it on a cluster of nodes by specifying `nodes`.

<div editor-title="examples/distributed-training/torchrun/.dstack.yml">

```yaml
type: task
name: train-distrib

nodes: 2

python: 3.12
env:
  - NCCL_DEBUG=INFO
commands:
  - git clone https://github.com/pytorch/examples.git pytorch-examples
  - cd pytorch-examples/distributed/ddp-tutorial-series
  - uv pip install -r requirements.txt
  - |
    torchrun \
      --nproc-per-node=$DSTACK_GPUS_PER_NODE \
      --node-rank=$DSTACK_NODE_RANK \
      --nnodes=$DSTACK_NODES_NUM \
      --master-addr=$DSTACK_MASTER_NODE_IP \
      --master-port=12345 \
      multinode.py 50 10

resources:
  gpu: 24GB:1..2
  shm_size: 24GB
```

</div>

Nodes can communicate using their private IP addresses.
Use `DSTACK_MASTER_NODE_IP`, `DSTACK_NODES_IPS`, `DSTACK_NODE_RANK`, and other
[System environment variables](#system-environment-variables) for inter-node communication.

`dstack` is easy to use with `accelerate`, `torchrun`, Ray, Spark, and any other distributed frameworks.


!!! info "MPI"
    If want to use MPI, you can set `startup_order` to `workers-first` and `stop_criteria` to `master-done`, and use `DSTACK_MPI_HOSTFILE`.
    See the [NCCL](../../examples/clusters/nccl-tests/index.md) or [RCCL](../../examples/clusters/rccl-tests/index.md) examples.

> For detailed examples, see [distributed training](../../examples.md#distributed-training) examples.

??? info "Network interface"
    Distributed frameworks usually detect the correct network interface automatically,
    but sometimes you need to specify it explicitly.

    For example, with PyTorch and the NCCL backend, you may need
    to add these commands to tell NCCL to use the private interface:

    ```yaml
    commands:
      - apt-get install -y iproute2
      - >
        if [[ $DSTACK_NODE_RANK == 0 ]]; then
          export NCCL_SOCKET_IFNAME=$(ip -4 -o addr show | fgrep $DSTACK_MASTER_NODE_IP | awk '{print $2}')
        else
          export NCCL_SOCKET_IFNAME=$(ip route get $DSTACK_MASTER_NODE_IP | sed -E 's/.*?dev (\S+) .*/\1/;t;d')
        fi
      # ... The rest of the commands
    ```

??? info "SSH"
    You can log in to any node from any node via SSH on port 10022 using the `~/.ssh/dstack_job` private key.
    For convenience, `~/.ssh/config` is preconfigured with these options, so a simple `ssh <node_ip>` is enough.
    For a list of nodes IPs check the `DSTACK_NODES_IPS` environment variable.

!!! info "Fleets"
    Distributed tasks can only run on fleets with
    [cluster placement](fleets.md#cloud-placement).
    While `dstack` can provision such fleets automatically, it is
    recommended to create them via a fleet configuration
    to ensure the highest level of inter-node connectivity.

> See the [Clusters](../guides/clusters.md) guide for more details on how to use `dstack` on clusters.

### Resources

When you specify a resource value like `cpu` or `memory`,
you can either use an exact value (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: trl-sft    

python: 3.12

env:
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE
  
resources:
  # 16 or more x86_64 cores
  cpu: 16..
  # 200GB or more RAM
  memory: 200GB..
  # 4 GPUs from 40GB to 80GB
  gpu: 40GB..80GB:4
  # Shared memory (required by multi-gpu)
  shm_size: 24GB
  # Disk size
  disk: 500GB
```

</div>

The `cpu` property lets you set the architecture (`x86` or `arm`) and core count — e.g., `x86:16` (16 x86 cores), `arm:8..` (at least 8 ARM cores). 
If not set, `dstack` infers it from the GPU or defaults to `x86`.

The `gpu` property lets you specify vendor, model, memory, and count — e.g., `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either), `A100:80GB` (one 80GB A100), `A100:2` (two A100), `24GB..40GB:2` (two GPUs with 24–40GB), `A100:40GB:2` (two 40GB A100s). 

If vendor is omitted, `dstack` infers it from the model or defaults to `nvidia`.

<!-- ??? info "Google Cloud TPU"
    To use TPUs, specify its architecture via the `gpu` property.

    <!-- TODO: Add a TRL TPU example -->

    ```yaml
    type: task
    name: train    
    
    python: 3.12
    
    commands:
      - pip install -r fine-tuning/qlora/requirements.txt
      - python fine-tuning/qlora/train.py
    
    resources:
      gpu: v2-8
    ```

    Currently, only 8 TPU cores can be specified, supporting single TPU device workloads. Multi-TPU support is coming soon. -->

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `24GB`.

> If you’re unsure which offers (hardware configurations) are available from the configured backends, use the
> [`dstack offer`](../reference/cli/dstack/offer.md#list-gpu-offers) command to list them.


### Docker

#### Default image

If you don't specify `image`, `dstack` uses its base Docker image pre-configured with 
`uv`, `python`, `pip`, essential CUDA drivers, and NCCL tests (under `/opt/nccl-tests/build`). 

Set the `python` property to pre-install a specific version of Python.

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: train    

python: 3.12

env:
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1..2
  shm_size: 24GB
```

</div>

#### NVCC

By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
If you need `nvcc`, set the [`nvcc`](../reference/dstack.yml/dev-environment.md#nvcc) property to true.

```yaml
type: task
name: train    

python: 3.12
nvcc: true

env:
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - uv pip install flash_attn --no-build-isolation
  - |
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET \
      --attn_implementation=flash_attention_2 \
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1
```

#### Custom image

If you want, you can specify your own Docker image via `image`.

<!-- TODO: Automatically detect the shell -->

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: trl-sft

image: huggingface/trl-latest-gpu

env:
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

# if shell is not specified, `sh` is used for custom images
shell: bash

commands:
  - source activate trl
  - |
    trl sft --model_name_or_path $MODEL \
        --dataset_name $DATASET \
        --output_dir /output \
        --torch_dtype bfloat16 \
        --use_peft true

resources:
  gpu: H100:1
```

</div>

#### Docker in Docker

Set `docker` to `true` to enable the `docker` CLI in your task, e.g., to run or build Docker images, or use Docker Compose.

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: docker-nvidia-smi

docker: true

commands:
  - docker run --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi

resources:
  gpu: 1
```

</div>

Cannot be used with `python` or `image`. Not supported on `runpod`, `vastai`, or `kubernetes`.

#### Privileged mode

To enable privileged mode, set [`privileged`](../reference/dstack.yml/dev-environment.md#privileged) to `true`.

Not supported with `runpod`, `vastai`, and `kubernetes`.

#### Private registry
    
Use the [`registry_auth`](../reference/dstack.yml/dev-environment.md#registry_auth) property to provide credentials for a private Docker registry. 

```yaml
type: task
name: train

env:
  - NGC_API_KEY

image: nvcr.io/nvidia/pytorch:25.05-py3
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}

commands:
  - git clone https://github.com/pytorch/examples.git pytorch-examples
  - cd pytorch-examples/distributed/ddp-tutorial-series
  - pip install -r requirements.txt
  - |
    torchrun \
      --nproc-per-node=$DSTACK_GPUS_PER_NODE \
      --nnodes=$DSTACK_NODES_NUM \
      multinode.py 50 10

resources:
  gpu: H100:1..2
  shm_size: 24GB
```

### Environment variables

<div editor-title=".dstack.yml"> 

```yaml
type: task
name: trl-sft    

python: 3.12

env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1
```

</div>

If you don't assign a value to an environment variable (see `HF_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

<span id="system-environment-variables"></span>
??? info "System environment variables"
    The following environment variables are available in any run by default:
    
    | Name                    | Description                                                      |
    |-------------------------|------------------------------------------------------------------|
    | `DSTACK_RUN_NAME`       | The name of the run                                              |
    | `DSTACK_REPO_ID`        | The ID of the repo                                               |
    | `DSTACK_GPUS_NUM`       | The total number of GPUs in the run                              |
    | `DSTACK_NODES_NUM`      | The number of nodes in the run                                   |
    | `DSTACK_GPUS_PER_NODE`  | The number of GPUs per node                                      |
    | `DSTACK_NODE_RANK`      | The rank of the node                                             |
    | `DSTACK_MASTER_NODE_IP` | The internal IP address of the master node                          |
    | `DSTACK_NODES_IPS`      | The list of internal IP addresses of all nodes delimited by "\n" |
    | `DSTACK_MPI_HOSTFILE`   | The path to a pre-populated MPI hostfile                         |

### Files

Sometimes, when you run a task, you may want to mount local files. This is possible via the [`files`](../reference/dstack.yml/task.md#_files) property. Each entry maps a local directory or file to a path inside the container.

<div editor-title="examples/.dstack.yml"> 

```yaml
type: task
name: trl-sft

files:
  - .:examples  # Maps the directory where `.dstack.yml` to `/workflow/examples`
  - ~/.ssh/id_rsa:/root/.ssh/id_rsa  # Maps `~/.ssh/id_rsa` to `/root/.ssh/id_rs

python: 3.12

env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1
```

</div>

Each entry maps a local directory or file to a path inside the container. Both local and container paths can be relative or absolute.

If the local path is relative, it’s resolved relative to the configuration file. If the container path is relative, it’s resolved relative to `/workflow`.

The container path is optional. If not specified, it will be automatically calculated.

<!-- TODO: Add a more elevant example -->

<div editor-title="examples/.dstack.yml"> 

```yaml
type: task
name: trl-sft    

files:
  - ../examples  # Maps `examples` (the parent directory of `.dstack.yml`) to `/workflow/examples`
  - ~/.cache/huggingface/token  # Maps `~/.cache/huggingface/token` to `/root/~/.cache/huggingface/token`

python: 3.12

env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1
```

</div>

??? info "Upload limit and excludes"
    Whether its a file or folder, each entry is limited to 2MB. To avoid exceeding this limit, make sure to exclude unnecessary files
    by listing it via `.gitignore` or `.dstackignore`.
    The 2MB upload limit can be increased by setting the `DSTACK_SERVER_CODE_UPLOAD_LIMIT` environment variable.

### Repos

Sometimes, you may want to mount an entire Git repo inside the container.

Imagine you have a cloned Git repo containing an `examples` subdirectory with a `.dstack.yml` file:

<!-- TODO: Add a more elevant example -->

<div editor-title="examples/.dstack.yml"> 

```yaml
type: task
name: trl-sft    

repos:
  # Mounts the parent directory of `examples` (must be a Git repo)
  #   to `/workflow` (the default working directory)
  - ..

python: 3.12

env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1
  - MODEL=Qwen/Qwen2.5-0.5B
  - DATASET=stanfordnlp/imdb

commands:
  - uv pip install trl
  - | 
    trl sft \
      --model_name_or_path $MODEL --dataset_name $DATASET
      --num_processes $DSTACK_GPUS_PER_NODE

resources:
  gpu: H100:1
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

    <!-- TODO: Add a more elevant example -->

    <div editor-title="examples/.dstack.yml"> 

    ```yaml
    type: task
    name: trl-sft    

    repos:
      # Clone the specified repo to `/workflow` (the default working directory)
      - https://github.com/dstackai/dstack

    python: 3.12

    env:
      - HF_TOKEN
      - HF_HUB_ENABLE_HF_TRANSFER=1
      - MODEL=Qwen/Qwen2.5-0.5B
      - DATASET=stanfordnlp/imdb

    commands:
      - uv pip install trl
      - | 
        trl sft \
          --model_name_or_path $MODEL --dataset_name $DATASET
          --num_processes $DSTACK_GPUS_PER_NODE

    resources:
      gpu: H100:1
    ```

    </div>

??? info "Private repos"
    If a Git repo is private, `dstack` will automatically try to use your default Git credentials (from
    `~/.ssh/config` or `~/.config/gh/hosts.yml`).

    If you want to use custom credentials, you can provide them with [`dstack init`](../reference/cli/dstack/init.md).

> Currently, you can configure up to one repo per run configuration.

### Retry policy

By default, if `dstack` can't find capacity, or the task exits with an error, or the instance is interrupted, 
the run will fail.

If you'd like `dstack` to automatically retry, configure the 
[retry](../reference/dstack.yml/task.md#retry) property accordingly:

<!-- TODO: Add a relevant example -->

<div editor-title=".dstack.yml">

```yaml
type: task
name: train    

python: 3.12

commands:
  - uv pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

retry:
  on_events: [no-capacity, error, interruption]
  # Retry for up to 1 hour
  duration: 1h
```

</div>

If one job of a multi-node task fails with retry enabled,
`dstack` will stop all the jobs and resubmit the run.

### Priority

Be default, submitted runs are scheduled in the order they were submitted.
When compute resources are limited, you may want to prioritize some runs over others.
This can be done by specifying the [`priority`](../reference/dstack.yml/task.md) property in the run configuration:

<!-- TODO: Add a relevant example -->

<div editor-title=".dstack.yml">

```yaml
type: task
name: train

python: 3.12

commands:
  - uv pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

priority: 50
```

</div>

`dstack` tries to provision runs with higher priority first.
Note that if a high priority run cannot be scheduled,
it does not block other runs with lower priority from scheduling.

### Utilization policy

Sometimes it’s useful to track whether a task is fully utilizing all GPUs. While you can check this with
[`dstack metrics`](../reference/cli/dstack/metrics.md), `dstack` also lets you set a policy to auto-terminate the run if any GPU is underutilized.

Below is an example of a task that auto-terminate if any GPU stays below 10% utilization for 1 hour.

<!-- TODO: Add a relevant example -->

<div editor-title=".dstack.yml">

```yaml
type: task
name: train

python: 3.12
commands:
  - uv pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

resources:
  gpu: H100:8

utilization_policy:
  min_gpu_utilization: 10
  time_window: 1h
```

</div>

### Schedule

Specify `schedule` to start a task periodically at specific UTC times using the cron syntax:

<div editor-title=".dstack.yml">

```yaml
type: task
name: train

python: 3.12
commands:
  - uv pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

resources:
  gpu: H100:8

schedule:
  cron: "15 23 * * *" # everyday at 23:15 UTC
```

</div>

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
via the [`spot_policy`](../reference/dstack.yml/task.md#spot_policy) property. It accepts `spot`, `on-demand`, and `auto`.

--8<-- "docs/concepts/snippets/manage-fleets.ext"

!!! info "Reference"
    Tasks support many more configuration options,
    incl. [`backends`](../reference/dstack.yml/task.md#backends), 
    [`regions`](../reference/dstack.yml/task.md#regions), 
    [`max_price`](../reference/dstack.yml/task.md#max_price), and
    [`max_duration`](../reference/dstack.yml/task.md#max_duration), 
    among [others](../reference/dstack.yml/task.md).

--8<-- "docs/concepts/snippets/manage-runs.ext"

!!! info "What's next?"
    1. Read about [dev environments](dev-environments.md) and [services](services.md)
    2. Learn how to manage [fleets](fleets.md)
    3. Check the [Axolotl](/examples/single-node-training/axolotl) example
