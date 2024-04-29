# Tasks

Tasks allow for convenient scheduling of various batch jobs, such as training, fine-tuning, or
data processing, as well as running web applications.

You can run tasks on a single machine or on a cluster of nodes.

## Configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

<div editor-title="train.dstack.yml"> 

```yaml
type: task

# Specify the Python version, or your Docker image
python: "3.11"

# Specify environment variables
env:
  - HF_HUB_ENABLE_HF_TRANSFER=1

# The commands to run on start of the task
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

# Specify GPU, disk, and other resource requirements
resources:
  gpu: 80GB
```

</div>

> See the [.dstack.yml reference](../reference/dstack.yml/task.md) for more details.

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

### Environment variables

Environment variables can be set either within the configuration file or passed via the CLI.

```yaml
type: task

python: "3.11"
env:
  - HUGGING_FACE_HUB_TOKEN
  - HF_HUB_ENABLE_HF_TRANSFER=1
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

resources:
  gpu: 80GB
```

If you don't assign a value to an environment variable (see `HUGGING_FACE_HUB_TOKEN` above), 
`dstack` will require the value to be passed via the CLI or set in the current process.

For instance, you can define environment variables in a `.env` file and utilize tools like `direnv`.

### Ports

A task can configure ports. In this case, if the task is running an application on a port, `dstack run` 
will securely allow you to access this port from your local machine through port forwarding.

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"
env:
  - HF_HUB_ENABLE_HF_TRANSFER=1
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - tensorboard --logdir results/runs &
  - python fine-tuning/qlora/train.py
ports:
  - 6000

# (Optional) Configure `gpu`, `memory`, `disk`, etc
resources:
  gpu: 80GB
```

</div>

When running it, `dstack run` forwards `6000` port to `localhost:6000`, enabling secure access. 

??? info "Port mapping"
    By default, `dstack` uses the same ports on your local machine for port forwarding. However, you can override local ports using `--port`:
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f train.dstack.yml --port 6000:6001
    ```
    
    </div>
    
    This will forward the task's port `6000` to `localhost:6001`.

### Nodes

By default, the task runs on a single node. However, you can run it on a cluster of nodes.

<div editor-title="train.dstack.yml">

```yaml
type: task

# The size of the cluster
nodes: 2

python: "3.11"
env:
  - HF_HUB_ENABLE_HF_TRANSFER=1
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
All nodes are provisioned in the same region.

??? info "Backends"
    Running on multiple nodes is supported only with AWS, GCP, and Azure.

### Args

You can parameterize tasks with user arguments using `${{ run.args }}` in the configuration.

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11"
env:
  - HF_HUB_ENABLE_HF_TRANSFER=1
commands:
  - pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py ${{ run.args }}

resources:
  gpu: 80GB
```

</div>

Now, you can pass your arguments to the `dstack run` command:

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --train_batch_size=1 --num_train_epochs=100
```

</div>

The `dstack run` command will pass `--train_batch_size=1` and `--num_train_epochs=100` as arguments to `train.py`.

??? info "Profiles"
    In case you'd like to reuse certain parameters (such as spot policy, retry and max duration,
    max price, regions, instance types, etc.) across runs, you can define them via [`.dstack/profiles.yml`](../reference/profiles.yml.md).

## Running

To run a configuration, use the [`dstack run`](../reference/cli/index.md#dstack-run) command followed by the working directory path, 
configuration file path, and other options.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y

Provisioning...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

When `dstack` submits the task, it uses the current folder contents.

!!! info ".gitignore"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in `.gitignore`.

The `dstack run` command allows specifying many things, including spot policy, retry and max duration, 
max price, regions, instance types, and [much more](../reference/cli/index.md#dstack-run).

## Managing runs

**Stoping runs**

Once the run exceeds the max duration,
or when you use [`dstack stop`](../reference/cli/index.md#dstack-stop), 
the task and its cloud resources are deleted.

**Listing runs**

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## What's next?

1. Check the [QLoRA :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/qlora/README.md){:target="_blank"} example
2. Check the [`.dstack.yml` reference](../reference/dstack.yml/task.md) for more details and examples
3. Browse [all examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/README.md){:target="_blank"}