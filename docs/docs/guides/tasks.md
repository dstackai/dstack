# Tasks

A task can be any batch job or a web application that you may want to run on demand.

With `dstack`, you can define such a task through a configuration file and run it on one of the
configured clouds that offer the best price and availability.

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

The `.dstack.yml` has many other properties. To view them all, refer to the [Reference](../reference/dstack.yml/task.md).

## Run the task

To run a task, use the `dstack run` command followed by the path to the directory you want to use as the
working directory.

If the configuration file is named other than `.dstack.yml`, pass its path via the `-f` argument.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml

 RUN            CONFIGURATION     USER   BACKEND  INSTANCE  RESOURCES        SPOT
 wet-mangust-7  train.dstack.yml  admin  aws      -         5xCPUs, 15987MB  auto  

Waiting for capacity... To exit, press Ctrl+C...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

The `dstack run` command provisions cloud resources, pre-installs the environment, code, runs the task, and establishes an
SSH tunnel for secure access.

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

### Configure resources, price, etc

For every run, you can specify hardware resources like memory and GPU, along with various run policies (e.g., maximum
hourly price, use of spot instances, etc.).

| Example                     | Description                                |
|-----------------------------|--------------------------------------------|
| `dstack run . --gpu A10`    | Use an instance with `NVIDIA A10` GPU      |
| `dstack run . --gpu A100:8` | Use an instance with 8 `NVIDIA A100` GPUs  |
| `dstack run . --gpu 24GB`   | Use an instance with a GPU that has `24GB` |

The `dstack run` command has many options. To view them, refer to the [Reference](../reference/cli/run.md).

??? info "Profiles"
    ### Configure profiles (optional)

    Instead of configuring resources, price, and policies through `dstack run`, you can use profiles. To set up a profile, 
    create the `.dstack/profiles.yml` file in the root folder of the project. 
    
    <div editor-title=".dstack/profiles.yml"> 
    
    ```yaml
    profiles:
      - name: large

        resources:
          memory: 24GB  # (Optional) The minimum amount of RAM memory
          gpu:
            memory: 48GB  # (Optional) The minimum amount of GPU memory 

        retry_policy: # (Optional)
          limit: 30min
            
        max_price: 1.5 # (Optional) The maximim price per instance, in dollards.

        max_duration: 1d # (Optional) The maximum duration of the run.

        spot_policy: auto # (Optional) The spot policy. Supports `spot`, `on-demand, and `auto`.

        backends: [azure, lambda]  # (Optional) Use only listed backends 

        default: true # (Optional)
    ```
    
    </div>

    #### Spot instances

    If `spot_policy` is set to `auto`, `dstack` gives priority to spot instances. If unavailable, it uses on-demand instances. 
    To reduce costs, set `spot_policy` to `spot`. Keep in mind that spot instances are much cheaper but may be interrupted. 
    Your code should handle interruptions and resume from saved checkpoints.

    #### Retry policy

    If `dstack` can't find capacity, an error displays. To enable continuous capacity search, use `retry_policy` with a 
    `limit`. For example, setting it to `30min` makes `dstack` search for capacity for 30 minutes.

    #### Default profile
    
    By default, the `dstack run` command uses the default profile. You 
    can override it by passing the `--profile` argument to the `dstack run` command.
    
    For more details on the syntax of the `profiles.yml` file, refer to the [Reference](../reference/profiles.yml.md).

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