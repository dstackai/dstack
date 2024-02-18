# Tasks

Tasks are perfect for scheduling all kinds of jobs (e.g., training, fine-tuning, processing data, batch inference, etc.)
as well as running web applications.

[//]: # (TODO: Support multi-node)

You simply specify the commands, required environment, and resources, and then submit it. dstack provisions the required
resources in a configured backend and runs the task.

## Using the CLI

### Define a configuration

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

# (Optional) Configure `gpu`, `memory`, `disk`, etc
resources:
  gpu: 80GB
```

</div>

The YAML file allows you to specify your own Docker image, environment variables, 
resource requirements, etc.
If image is not specified, `dstack` uses its own (pre-configured with Python, Conda, and essential CUDA drivers).

For more details on the file syntax, refer to [`.dstack.yml`](../reference/dstack.yml.md).

### Run the configuration

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

# (Optional) Configure `gpu`, `memory`, `disk`, etc
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

### Configure policies

For a run, multiple policies can be configured, such as spot policy, retry policy, max duration, max price, etc.

By default, if `dstack` is unable to find capacity, `dstack run` will fail. However, the retry policy
may be used to let `dstack` re-submit the run automatically until it finds capacity. 

Policies can be configured either via [`dstack run`](../reference/cli/index.md#dstack-run)
or [`.dstack/profiles.yml`](../reference/profiles.yml.md).
For more details on policies and their defaults, refer to [`.dstack/profiles.yml`](../reference/profiles.yml.md).

## Manage runs

### Stop a run

Once the run exceeds the max duration,
or when you use [`dstack stop`](../reference/cli/index.md#dstack-stop), 
the task and its cloud resources are deleted.

### List runs 

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## Using the API

Submitting and managing tasks is also possible programmatically via the [Python API](../reference/api/python/index.md) or 
[REST API](../reference/api/rest/index.md).

!!! info "What's next?"
    1. Check the [QLoRA](../../examples/qlora.md) example
    2. Read about [dev environments](../concepts/dev-environments.md) and [services](../concepts/services.md)
    3. Browse [examples](../../examples/index.md)
    4. Check the [reference](../reference/dstack.yml.md)