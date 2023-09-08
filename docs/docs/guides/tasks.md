# Tasks

A task in `dstack` can be a batch job or a web app for on-demand execution. When running a web app as a task, `dstack`
conveniently forwards the application's ports to your local machine.

!!! info "NOTE:"
    Tasks are ideal for batch jobs (such as training or fine-tuning), as well as for running web apps (e.g., LLMs) for
    development purposes. If you intend to run a web app for production purposes, please refer to [services](services.md).

## Define a configuration

To configure a task, create its configuration file. It can be defined
in any folder but must be named with a suffix `.dstack.yml`.

<div editor-title="train.dstack.yml"> 

```yaml
type: task

python: "3.11" # (Optional) If not specified, your local version is used.

commands:
  - pip install -r requirements.txt
  - python train.py
```

</div>

### Forward ports

A task can configure ports to allow `dstack` to forward them to your local machine, enabling secure access from your local
machine while the CLI is attached.

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

??? info "Port mapping"
    If you've configured ports, the CLI forwards them to your local machine, using the same port numbers. 
    Yet, you can choose to override the local ports if needed.
    
    The following command will make the application available on `http://127.0.0.1:3000`.
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f serve.dstack.yml --port 3000:7860
    ```
    
    </div>

    Alternatively, you can hardcode the port mapping directly into the configuration (not recommended):

    <div editor-title="serve.dstack.yml"> 

    ```yaml
    type: task
    
    ports:
      - 3000:7860
    
    commands:
      - pip install -r requirements.txt
      - gradio app.py
    ```
    
    </div>

### Configure the environment

By default, `dstack` uses its own Docker images to run tasks, which are pre-configured with Python, Conda, and essential CUDA drivers.

You can install packages using `pip` and `conda` executables from `commands`.

??? info "Docker image"
    If you prefer to use your custom Docker image, use the `image` property in the configuration.

    <div editor-title=".dstack.yml">

    ```yaml
    type: task
    
    image: nvcr.io/nvidia/pytorch:22.12-py3
    
    commands:
      - pip install -r requirements.txt 
      - python train.py
    ```

    </div>

??? info "Build command (experimental)" 

    In case you'd like to pre-build the environment rather than install packaged on every run,
    you can use the `build` property. Here's an example:
    
    <div editor-title="train.dstack.yml"> 
    
    ```yaml
    type: task

    python: "3.11" # (Optional) If not specified, your local version is used.
    
    build:
      - pip install -r requirements.txt
    
    commands:
      - python train.py
    ```
    
    </div>

    In this case, you have to pass `--build` to `dstack run`.

    <div class="termy">
    
    ```shell
    $ dstack run . -f train.dstack.yml --build
    ```
    
    </div>

    If there is no pre-built image, the `dstack run` command will build it and upload it to the storage. If the pre-built
    image is already available, the `dstack run` command will reuse it.

For more details on the file syntax, refer to [`.dstack.yml`](../reference/dstack.yml/task.md).

## Run the configuration

To run a task, use the `dstack run` command followed by the path to the directory you want to use as the
working directory.

If the configuration file is named other than `.dstack.yml`, pass its path via the `-f` argument.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml

 RUN            CONFIGURATION     BACKEND  RESOURCES        SPOT  PRICE
 wet-mangust-7  train.dstack.yml  aws      5xCPUs, 15987MB  yes   $0.0547  

Waiting for capacity... To exit, press Ctrl+C...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

The `dstack run` command provisions cloud resources, pre-installs the environment, code, runs the task, and establishes an
SSH tunnel for secure access.

### Parametrize tasks

If you want, it's possible to parametrize tasks with user arguments. Here's an example:

<div editor-title="args.dstack.yml"> 

```yaml
type: task

commands:
  - python train.py ${{ run.args }}
```

</div>

Now, you can pass your arguments to the `dstack run` command:

<div class="termy">

```shell
$ dstack run . -f args.dstack.yml --train_batch_size=1 --num_train_epochs=100
```

</div>

The `dstack run` command will pass `--train_batch_size=1` and `--num_train_epochs=100` as arguments to `train.py`.

### Configure a retry limit

By default, tf `dstack` is unable to find capacity, the `dstack run` command will fail. However, you may
pass the [`--retry-limit`](../reference/cli/run.md#RETRY_LIMIT) option to `dstack run` to specify the timeframe in which `dstack` should search for
capacity and automatically resubmit the run.

Here's an example of the command, wait for available capacity for up to three hours:

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml --retry-limit 3h
```

</div>

### Requesting resources

You can request resources using the [`--gpu`](../reference/cli/run.md#GPU) 
and [`--memory`](../reference/cli/run.md#MEMORY) arguments with `dstack run`, 
or through [`resources`](../reference/profiles.yml.md#RESOURCES) with `.dstack/profiles.yml`.

Both the [`dstack run`](../reference/cli/run.md) command and [`.dstack/profiles.yml`](../reference/profiles.yml.md)
support various other options, including requesting spot instances, defining the maximum run duration or price, and
more.

!!! info "Automatic instance discovery"
    `dstack` will automatically select the suitable instance type from a cloud provider and region with the best
    price and availability.

??? info "Reload mode (experimental)"

    Some web development frameworks like Gradio, Streamlit, and FastAPI support auto-reloading. With `dstack run`, you can
    enable the reload mode by using the `--reload` argument.
    
    <div class="termy">
    
    ```shell
    $ dstack run . -f serve.dstack.yml --reload
    ```
    
    </div>
    
    This feature allows you to run an app in the cloud while continuing to edit the source code locally and have the app
    reload changes on the fly.

For more details on the run command, refer to [`dstack run`](../reference/cli/run.md).