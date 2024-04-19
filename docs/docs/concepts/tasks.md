# Tasks

Tasks allow for convenient scheduling of any kind of batch jobs, such as training, fine-tuning, or data processing, as
well as running web applications.

[//]: # (TODO: Support multi-node)

You simply specify the commands, required environment, and resources, and then submit it. `dstack` provisions the required
resources in a configured backend and runs the task.

## Define a configuration

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
  - python fine-tuning/qlora/train.py

resources:
  gpu: 80GB
```

</div>

The YAML file allows you to specify your own Docker image, environment variables, 
resource requirements, etc.
If image is not specified, `dstack` uses its own (pre-configured with Python, Conda, and essential CUDA drivers).

!!! info ".dstack.yml"
    For more details on the file syntax, refer to the [`.dstack.yml` reference](../reference/dstack.yml/task.md).

### Configure environment variables

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

### Configure ports

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

??? info "Override port mapping"
    By default, `dstack` uses the same ports on your local machine for port forwarding. However, you can override local ports using `--port`:
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f train.dstack.yml --port 6000:6001
    ```
    
    </div>
    
    This will forward the task's port `6000` to `localhost:6001`.

### Parametrize tasks

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

## Run the configuration

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

!!! info "Exclude files"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in either `.gitignore` or `.dstackignore`.

The `dstack run` command allows specifying many things, including spot policy, retry and max duration, 
max price, regions, instance types, and [much more](../reference/cli/index.md#dstack-run).

## Configure profiles

In case you'd like to reuse certain parameters (such as spot policy, retry and max duration, 
max price, regions, instance types, etc.) across runs, you can define them via [`.dstack/profiles.yml`](../reference/profiles.yml.md).

## Manage runs

### Stop a run

Once the run exceeds the max duration,
or when you use [`dstack stop`](../reference/cli/index.md#dstack-stop), 
the task and its cloud resources are deleted.

### List runs 

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## What's next?

1. Check the [QLoRA :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/fine-tuning/qlora/README.md) example
2. Check the [`.dstack.yml` reference](../reference/dstack.yml/task.md) for more details and examples
3. Browse [all examples :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/README.md)