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

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).


!!! info "Nodes"
    By default, tasks run on a single instance. However, you can specify
    the [number of nodes](../reference/dstack.yml/task.md#_nodes).
    In this case, `dstack` provisions a cluster of instances.

> See the [.dstack.yml reference](../reference/dstack.yml/task.md)
> for many examples on task configuration.

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

TensorBoard 2.13.0 at http://localhost:6006/ (Press CTRL+C to quit)

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

If the task specifies `ports`, `dstack run` automatically forwards them to your local machine for
convenient and secure access.

When running the task, `dstack run` mounts the current folder's contents.

!!! info ".gitignore"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in `.gitignore`.

> See the [CLI reference](../reference/cli/index.md#dstack-run) for more details
> on how `dstack run` works.

## Managing runs

**Stoping runs**

Once you use [`dstack stop`](../reference/cli/index.md#dstack-stop) (or when the run exceeds the
`max_duration`), the instances return to the [pool](pools.md).

**Listing runs**

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## What's next?

1. Check the [QLoRA :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/qlora/README.md){:target="_blank"} example
2. Check the [`.dstack.yml` reference](../reference/dstack.yml/task.md) for more details and examples
3. Browse [all examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/tree/master/examples){:target="_blank"}