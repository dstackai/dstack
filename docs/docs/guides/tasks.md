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

python: "3.11" # (Optional) If not specified, your local version is used

commands:
  - pip install -r requirements.txt
  - python train.py
```

</div>

A task can configure ports:

<div editor-title="serve.dstack.yml"> 

```yaml
type: task

ports:
  - 7860

python: "3.11" # (Optional) If not specified, your local version is used.

commands:
  - pip install -r requirements.txt
  - gradio app.py
```

</div>

When running a task, `dstack` forwards the remote ports to `localhost` for secure 
and convenient access.

By default, `dstack` uses its own Docker images to run dev environments, 
which are pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, ports, environment variables, and many other 
    options.
    For more details, refer to the [Reference](../reference/dstack.yml.md#task).

### Run the configuration

To run a configuration, use the `dstack run` command followed by the working directory path, 
configuration file path, and any other options (e.g., for requesting hardware resources).

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --gpu A100

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
    The `dstack run` command allows you to use `--gpu` to request GPUs (e.g. `--gpu A100` or `--gpu 80GB` or `--gpu A100:4`, etc.),
    and many other options (incl. spot instances, disk size, max price, max duration, retry policy, etc.).
    For more details, refer to the [Reference](../reference/cli/index.md#dstack-run).

??? info "Port mapping"
    When running a task, `dstack` forwards the remote ports to `localhost` for secure 
    and convenient access.
    You can override local ports via `--port`:
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f serve.dstack.yml --port 8080:7860
    ```
    
    </div>
    
    This will forward the task's port `7860` to `localhost:8080`.

### Parametrize tasks

You can parameterize tasks with user arguments using `${{ run.args }}` in the configuration.

Example:

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used

commands:
  - pip install -r requirements.txt
  - python train.py ${{ run.args }}
```

</div>

Now, you can pass your arguments to the `dstack run` command:

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --gpu A100 --train_batch_size=1 --num_train_epochs=100
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

[//]: # (Using the API)

## What's next?

1. Check the [QLoRA](../../learn/qlora.md) example
2. Read about [dev environments](../guides/dev-environments.md) 
    and [services](../guides/services.md)
3. See all [learning materials](../../learn/index.md)
4. Check the [reference](../reference/dstack.yml.md#task)