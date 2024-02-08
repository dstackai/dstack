# Tasks

With `dstack`, you can use the CLI or API to run tasks like training scripts, batch jobs, or web apps. 
Provide the commands, ports, and choose the Python version or a Docker image.

`dstack` handles the execution on configured cloud GPU provider(s) with the necessary resources.

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

By default, `dstack` uses its own Docker images to run dev environments, 
which are pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, ports, environment variables, and many other 
    options. For more details, refer to the [Reference](../reference/dstack.yml.md#task).

### Run the configuration

To run a configuration, use the `dstack run` command followed by the working directory path, 
configuration file path, and any other options (e.g., for requesting hardware resources).

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

!!! info "Run options"
    The `dstack run` command allows you to use specify the spot policy (e.g. `--spot-auto`, `--spot`, or `--on-demand`), 
    max duration of the run (e.g. `--max-duration 1h`), and many other options.
    For more details, refer to the [Reference](../reference/cli/index.md#dstack-run).

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

### Configure retry limit

By default, if `dstack` is unable to find capacity, `dstack run` will fail. However, you may
pass the [`--retry-limit`](../reference/cli/index.md#dstack-run) option to `dstack run` to specify the timeframe in which `dstack` should search for
capacity and automatically resubmit the run.

Example:

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --retry-limit 3h
```

</div>

For more details on the `dstack run` command, refer to the [Reference](../reference/cli/index.md#dstack-run).

## Using the API

Submitting and managing tasks is also possible programmatically via the [Python API](../reference/api/python/index.md) or 
[REST API](../reference/api/rest/index.md).

## What's next?

1. Check the [QLoRA](../../examples/qlora.md) example
2. Read about [dev environments](../concepts/dev-environments.md) 
    and [services](../concepts/services.md)
3. Browse [examples](../../examples/index.md)
4. Check the [reference](../reference/dstack.yml.md#task)