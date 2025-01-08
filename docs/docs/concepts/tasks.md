# Tasks

A task allows you to run arbitrary commands on one or more nodes.
They are best suited for jobs like training or batch processing.

## Define a configuration

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
    # 24GB or more vRAM
    memory: 24GB..
    # Two or more GPU
    count: 2..
```

</div>

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

<div editor-title="examples/fine-tuning/train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train-distrib

# The size of the cluster
nodes: 2

python: "3.10"

# Commands of the task
commands:
  - pip install -r requirements.txt
  - torchrun
    --nproc_per_node=$DSTACK_GPUS_PER_NODE
    --node_rank=$DSTACK_NODE_RANK
    --nnodes=$DSTACK_NODES_NUM
    --master_addr=$DSTACK_MASTER_NODE_IP
    --master_port=8008 resnet_ddp.py
    --num_epochs 20

resources:
  gpu: 24GB
```

</div>

All you need to do is pass the corresponding environment variables such as 
`DSTACK_GPUS_PER_NODE`, `DSTACK_NODE_RANK`, `DSTACK_NODES_NUM`,
`DSTACK_MASTER_NODE_IP`, and `DSTACK_GPUS_NUM` (see [System environment variables](#system-environment-variables)).

!!! info "Fleets"
    To ensure all nodes are provisioned into a cluster placement group and to enable the highest level of inter-node 
    connectivity (incl. support for [EFA :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}),
    create a [fleet](fleets.md) via a configuration before running a disstributed task.

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
image: dstackai/base:py3.13-0.6-cuda-12.1

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py
```

</div>

??? info "Private registry"
    Use the `registry_auth` property to provide credentials for a private Docker registry.

    ```yaml
    type: dev-environment
    # The name is optional, if not specified, generated randomly
    name: train
    
    # Any private Docker image
    image: dstackai/base:py3.13-0.6-cuda-12.1
    # Credentials of the private Docker registry
    registry_auth:
      username: peterschmidt85
      password: ghp_e49HcZ9oYwBzUbcSk2080gXZOU2hiT9AeSR5
    
    # Commands of the task
    commands:
      - pip install -r fine-tuning/qlora/requirements.txt
      - python fine-tuning/qlora/train.py
    ```

??? info "Privileged mode"
    All backends except `runpod`, `vastai`, and `kubernetes` support running containers in privileged mode.
    This mode enables features like using [Docker and Docker Compose](../guides/protips.md#docker-and-docker-compose) 
    inside `dstack` runs.

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
    | `DSTACK_MASTER_NODE_IP` | The internal IP address the master node                          |
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

## Run a configuration

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

### Retry policy

By default, if `dstack` can't find capacity, the task exits with an error, or the instance is interrupted, 
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

--8<-- "docs/concepts/snippets/manage-fleets.ext"

--8<-- "docs/concepts/snippets/manage-runs.ext"

!!! info "What's next?"
    1. Read about [dev environments](dev-environments.md), [services](services.md), and [repos](repos.md)
    2. Learn how to manage [fleets](fleets.md)
    3. Check the [Axolotl](/examples/fine-tuning/axolotl) example
