# task

The `task` configuration type allows running [tasks](../../tasks.md).

> Configuration files must be inside the project repo, and their names must end with `.dstack.yml` 
> (e.g. `.dstack.yml` or `train.dstack.yml` are both acceptable).
> Any configuration can be run via [`dstack apply`](../cli/index.md#dstack-apply).

## Examples

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

### Ports { #_ports }

A task can configure ports. In this case, if the task is running an application on a port, `dstack run` 
will securely allow you to access this port from your local machine through port forwarding.

<div editor-title="train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train    

python: "3.10"

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - tensorboard --logdir results/runs &
  - python fine-tuning/qlora/train.py
# Expose the port to access TensorBoard
ports:
  - 6000
```

</div>

When running it, `dstack run` forwards `6000` port to `localhost:6000`, enabling secure access.

[//]: # (See [tasks]&#40;../../tasks.md#configure-ports&#41; for more detail.)

### Docker

If you want, you can specify your own Docker image via `image`.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
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

!!! info "Docker and Docker Compose"
    All backends except `runpod`, `vastai` and `kubernetes` also allow to use [Docker and Docker Compose](../../guides/protips.md#docker-and-docker-compose) 
    inside `dstack` runs.

### Resources { #_resources }

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
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
      - pip install torch~=2.3.0 torch_xla[tpu]~=2.3.0 torchvision -f https://storage.googleapis.com/libtpu-releases/index.html
      - git clone --recursive https://github.com/pytorch/xla.git
      - python3 xla/test/test_train_mp_imagenet.py --fake_data --model=resnet50 --num_epochs=1

    resources:
      gpu: v2-8
    ```

    Currently, only 8 TPU cores can be specified, supporting single host workloads. Multi-host support is coming soon.

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

### Environment variables

<div editor-title="train.dstack.yml"> 

```yaml
type: task

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

> If you don't assign a value to an environment variable (see `HF_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.envrc` file and utilize tools like `direnv`.

##### System environment variables

The following environment variables are available in any run and are passed by `dstack` by default:

| Name                    | Description                             |
|-------------------------|-----------------------------------------|
| `DSTACK_RUN_NAME`       | The name of the run                     |
| `DSTACK_REPO_ID`        | The ID of the repo                      |
| `DSTACK_GPUS_NUM`       | The total number of GPUs in the run     |
| `DSTACK_NODES_NUM`      | The number of nodes in the run          |
| `DSTACK_NODE_RANK`      | The rank of the node                    |
| `DSTACK_MASTER_NODE_IP` | The internal IP address the master node |
| `DSTACK_NODES_IPS`      | The list of internal IP addresses of all nodes delimited by "\n" |

### Distributed tasks

By default, the task runs on a single node. However, you can run it on a cluster of nodes.

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

If you run the task, `dstack` first provisions the master node and then runs the other nodes of the cluster.

??? info "Network"
    To ensure all nodes are provisioned into a cluster placement group and to enable the highest level of inter-node 
    connectivity, it is recommended to manually create a  [fleet](../../concepts/fleets.md) before running a task.
    This won’t be needed once [this issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1805){:target="_blank"} 
    is fixed.

> `dstack` is easy to use with `accelerate`, `torchrun`, and other distributed frameworks. All you need to do
is pass the corresponding environment variables such as `DSTACK_GPUS_PER_NODE`, `DSTACK_NODE_RANK`, `DSTACK_NODES_NUM`,
`DSTACK_MASTER_NODE_IP`, and `DSTACK_GPUS_NUM` (see [System environment variables](#system-environment-variables)).

??? info "Backends"
    Running on multiple nodes is supported only with the `aws`, `gcp`, `azure`, `oci` backends, or
    [SSH fleets](../../concepts/fleets.md#ssh-fleets).

    Additionally, the `aws` backend supports [Elastic Fabric Adapter :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}.
    For a list of instance types with EFA support see [Fleets](../../concepts/fleets.md#cloud-fleets).

### Web applications

Here's an example of using `ports` to run web apps with `tasks`. 

<div editor-title="app.dstack.yml"> 

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

### Spot policy

You can choose whether to use spot instances, on-demand instances, or any available type.

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train    

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Uncomment to leverage spot instances
#spot_policy: auto
```

</div>

The `spot_policy` accepts `spot`, `on-demand`, and `auto`. The default for tasks is `on-demand`.

### Queueing tasks { #queueing-tasks }

By default, if `dstack apply` cannot find capacity, the task fails. 

To queue the task and wait for capacity, specify the [`retry`](#retry) 
property:

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

retry:
  # Retry on no-capacity errors
  on_events: [no-capacity]
  # Retry within 1 day
  duration: 1d
```

</div>

### Backends

By default, `dstack` provisions instances in all configured backends. However, you can specify the list of backends:

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Use only listed backends
backends: [aws, gcp]
```

</div>

### Regions

By default, `dstack` uses all configured regions. However, you can specify the list of regions:

<div editor-title="train.dstack.yml">

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: train

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Use only listed regions
regions: [eu-west-1, eu-west-2]
```

</div>

### Volumes

Volumes allow you to persist data between runs.
To attach a volume, simply specify its name using the `volumes` property and specify where to mount its contents:

<div editor-title="train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: vscode    

python: "3.10"

# Commands of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Map the name of the volume to any path
volumes:
  - name: my-new-volume
    path: /volume_data
```

</div>

Once you run this configuration, the contents of the volume will be attached to `/volume_data` inside the task, 
and its contents will persist across runs.

??? Info "Instance volumes"
    If data persistence is not a strict requirement, use can also use
    ephemeral [instance volumes](../../concepts/volumes.md#instance-volumes).

!!! info "Limitations"
    When you're running a dev environment, task, or service with `dstack`, it automatically mounts the project folder contents
    to `/workflow` (and sets that as the current working directory). Right now, `dstack` doesn't allow you to 
    attach volumes to `/workflow` or any of its subdirectories.

The `task` configuration type supports many other options. See below.

## Root reference

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## `retry`

#SCHEMA# dstack._internal.core.models.profiles.ProfileRetry
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: retry-

## `resources`

#SCHEMA# dstack._internal.core.models.resources.ResourcesSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true
      item_id_prefix: resources-

## `resouces.gpu` { #resources-gpu data-toc-label="resources.gpu" }

#SCHEMA# dstack._internal.core.models.resources.GPUSpecSchema
    overrides:
      show_root_heading: false
      type:
        required: true

## `resouces.disk` { #resources-disk data-toc-label="resources.disk" }

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
