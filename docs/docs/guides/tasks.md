# Tasks

A task can be a batch job or a web app. Tasks can be used to run web apps for development purposes.

## Using the CLI

### Define a configuration

To run a task via the CLI, first create its configuration file. 
The configuration file name must end with `.dstack.yml` (e.g., `.dstack.yml` or `train.dstack.yml` are both acceptable).

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

When you run such a task, `dstack` forwards the configured ports to `localhost`.

By default, `dstack` uses its own Docker images to run dev environments, 
which are pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Configuration options"
    Configuration file allows you to specify a custom Docker image, ports, environment variables, and many other 
    options.
    For more details, refer to the [Reference](../reference/dstack.yml/task.md).

### Run the configuration

The `dstack run` command requires the working directory path, and optionally, the `-f`
argument pointing to the configuration file.

If the `-f` argument is not specified, `dstack` looks for the default configuration (`.dstack.yml`) in the working directory.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --gpu A100

 RUN            CONFIGURATION     BACKEND  RESOURCES        SPOT  PRICE
 wet-mangust-7  train.dstack.yml  aws      5xCPUs, 15987MB  yes   $0.0547  

Provisioning...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

#### Request resources

The `dstack run` command allows you to use `--gpu` to request GPUs (e.g. `--gpu A100` or `--gpu 80GB` or `--gpu A100:4`, etc.),
`--memory` to request memory (e.g. `--memory 128GB`),
and many other options (incl. spot instances, max price, max duration, etc.).

#### Override local ports

If your task configures ports, `dstack` forwards them to localhost using the same port. You can override the local port
through the CLI using `--port`:

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml --port 8080:7860
```

</div>

This will forward the task's port `7860` to `localhost:8080`.

#### Pass run arguments

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

#### Configure a retry limit

By default, tf `dstack` is unable to find capacity, the `dstack run` command will fail. However, you may
pass the [`--retry-limit`](../reference/cli/run.md#RETRY_LIMIT) option to `dstack run` to specify the timeframe in which `dstack` should search for
capacity and automatically resubmit the run.

Example:

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --retry-limit 3h
```

</div>

For more details on the `dstack run` command, refer to the [Reference](../reference/cli/run.md).

[//]: # (Using the API)