# Tasks

A task allows you to run arbitrary commands on one or more nodes.
They are best suited for jobs like training or batch processing.

## Apply a configuration

First, define a task configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

[//]: # (TODO: Make tabs - single machine & distributed tasks & web app)

<div editor-title="examples/fine-tuning/axolotl/train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: axolotl-train

# Using the official Axolotl's Docker image
image: winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1

# Required environment variables
env:
  - HF_TOKEN
  - WANDB_API_KEY
# Commands of the task
commands:
  - accelerate launch -m axolotl.cli.train examples/fine-tuning/axolotl/config.yaml

resources:
  gpu:
    # 24GB or more VRAM
    memory: 24GB..
    # Two or more GPU
    count: 2..
```

</div>

To run a task, pass the configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ dstack apply -f examples/.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:3  yes   $0.33

Submit the run axolotl-train? [y/n]: y

Launching `axolotl-train`...
---> 100%

{'loss': 1.4967, 'grad_norm': 1.2734375, 'learning_rate': 1.0000000000000002e-06, 'epoch': 0.0}
  0% 1/24680 [00:13<95:34:17, 13.94s/it]
  6% 73/1300 [00:48<13:57,  1.47it/s]
```

</div>

`dstack apply` automatically provisions instances, uploads the contents of the repo (incl. your local uncommitted changes),
and runs the commands.

## Configuration options

### Ports

A task can configure ports. In this case, if the task is running an application on a port, `dstack apply` 
will securely allow you to access this port from your local machine through port forwarding.

<div editor-title="train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: streamlit-hello

python: "3.10"

# Commands of the task
commands:
  - pip3 install streamlit
  - streamlit hello
# Expose the port to access the web app
ports: 
  - 8501
```

</div>

When running it, `dstack apply` forwards `8501` port to `localhost:8501`, enabling secure access to the running
application.

### Distributed tasks

By default, a task runs on a single node.
However, you can run it on a cluster of nodes by specifying `nodes`.

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train-distrib

# The size of the cluster
nodes: 2

python: "3.12"

# Commands to run on each node
commands:
  - git clone https://github.com/pytorch/examples.git
  - cd examples/distributed/ddp-tutorial-series
  - pip install -r requirements.txt
  - torchrun
    --nproc-per-node=$DSTACK_GPUS_PER_NODE
    --node-rank=$DSTACK_NODE_RANK
    --nnodes=$DSTACK_NODES_NUM
    --master-addr=$DSTACK_MASTER_NODE_IP
    --master-port=12345
    multinode.py 50 10

resources:
  gpu: 24GB
  # Uncomment if using multiple GPUs
  #shm_size: 24GB
```

</div>

Nodes can communicate using their private IP addresses.
Use `DSTACK_MASTER_NODE_IP`, `DSTACK_NODES_IPS`, `DSTACK_NODE_RANK`, and other
[System environment variables](#system-environment-variables)
to discover IP addresses and other details.

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

`dstack` is easy to use with `accelerate`, `torchrun`, Ray, Spark, and any other distributed frameworks.

### Resources

When you specify a resource value like `cpu` or `memory`,
you can either use an exact value (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train    

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
  
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
    type: task
    # The name is optional, if not specified, generated randomly
    name: train    
    
    python: "3.10"
    
    # Commands of the task
    commands:
      - pip install -r fine-tuning/qlora/requirements.txt
      - python fine-tuning/qlora/train.py
    
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

<div editor-title="train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train    

# If `image` is not specified, dstack uses its base image
python: "3.10"

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

??? info "nvcc"
    By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
    If you need `nvcc`, set the corresponding property to true.


    ```yaml
    type: task
    # The name is optional, if not specified, generated randomly
    name: train    

    # If `image` is not specified, dstack uses its base image
    python: "3.10"
    # Ensure nvcc is installed (req. for Flash Attention) 
    nvcc: true
    
    commands:
      - pip install -r fine-tuning/qlora/requirements.txt
      - python fine-tuning/qlora/train.py
    ```

### Docker

If you want, you can specify your own Docker image via `image`.

<div editor-title=".dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train    

# Any custom Docker image
image: dstackai/base:py3.13-0.7-cuda-12.1

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

!!! info "Privileged mode"
    To enable privileged mode, set [`privileged`](../reference/dstack.yml/task.md#privileged) to `true`.
    This mode allows using [Docker and Docker Compose](../guides/protips.md#docker-and-docker-compose) inside `dstack` runs.

    Not supported with `runpod`, `vastai`, and `kubernetes`.

??? info "Private registry"
    Use the [`registry_auth`](../reference/dstack.yml/task.md#registry_auth) property to provide credentials for a private Docker registry.

    ```yaml
    type: dev-environment
    # The name is optional, if not specified, generated randomly
    name: train
    
    # Any private Docker image
    image: dstackai/base:py3.13-0.7-cuda-12.1
    # Credentials of the private Docker registry
    registry_auth:
      username: peterschmidt85
      password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5
    
    # Commands of the task
    commands:
      - pip install -r fine-tuning/qlora/requirements.txt
      - python fine-tuning/qlora/train.py
    ```

### Environment variables

<div editor-title="train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train

python: "3.10"

# Environment variables
env:
  - HF_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
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

### Spot policy

By default, `dstack` uses on-demand instances. However, you can change that
via the [`spot_policy`](../reference/dstack.yml/task.md#spot_policy) property. It accepts `spot`, `on-demand`, and `auto`.

!!! info "Reference"
    Tasks support many more configuration options,
    incl. [`backends`](../reference/dstack.yml/task.md#backends), 
    [`regions`](../reference/dstack.yml/task.md#regions), 
    [`max_price`](../reference/dstack.yml/task.md#max_price), and
    [`max_duration`](../reference/dstack.yml/task.md#max_duration), 
    among [others](../reference/dstack.yml/task.md).

### Retry policy

By default, if `dstack` can't find capacity, or the task exits with an error, or the instance is interrupted, 
the run will fail.

If you'd like `dstack` to automatically retry, configure the 
[retry](../reference/dstack.yml/task.md#retry) property accordingly:

<div editor-title=".dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train    

python: "3.10"

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

retry:
  # Retry on specific events
  on_events: [no-capacity, error, interruption]
  # Retry for up to 1 hour
  duration: 1h
```

</div>

If one job of a multi-node task fails with retry enabled,
`dstack` will stop all the jobs and resubmit the run.

--8<-- "docs/concepts/snippets/manage-fleets.ext"

--8<-- "docs/concepts/snippets/manage-runs.ext"

!!! info "What's next?"
    1. Read about [dev environments](dev-environments.md), [services](services.md), and [repos](repos.md)
    2. Learn how to manage [fleets](fleets.md)
    3. Check the [Axolotl](/examples/fine-tuning/axolotl) example
