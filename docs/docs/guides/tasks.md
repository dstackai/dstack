# Tasks

A task can be any script that you may want to run on demand. For example, it could be
a training script, a script that processes data, or a web-based application.

With `dstack`, you can define such a task through a configuration file and run it in any cloud with a
single command.

## Configuration

To configure a task, create its configuration file. It can be defined
in any folder but must be named with a suffix `.dstack.yml`.

Here's an example:

<div editor-title="train.dstack.yml"> 

```yaml
type: task

commands:
  - pip install -r requirements.txt
  - python train.py
```

</div>

## Running a task

To run a task, use the `dstack run` command followed by the path to the directory you want to use as the
working directory during development.

If your configuration file has a name different from `.dstack.yml`, pass the path to it using the `-f` argument.

<div class="termy">

```shell
$ dstack run . -f train.dstack.yml

 RUN            CONFIGURATION     USER   PROJECT  INSTANCE  RESOURCES        SPOT
 wet-mangust-7  train.dstack.yml  admin  local    -         5xCPUs, 15987MB  auto  

Waiting for capacity... To exit, press Ctrl+C...
---> 100%

Epoch 0:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 1:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
Epoch 2:  100% 1719/1719 [00:18<00:00, 92.32it/s, loss=0.0981, acc=0.969]
```

</div>

This command provisions cloud resources, pre-installs the environment and code, and runs the script. If the task exposes
any ports, the command will forward them to your local machine for secure and convenient access.

??? info "Using .gitignore"
    When running a task, `dstack` uses the exact version of code that is present in the folder where you
    use the `dstack run` command.

    If your folder has large files or folders, this may affect the performance of the `dstack run` command. To avoid this,
    make sure to create a `.gitignore` file and include these large files or folders that you don't want to include when
    running dev environments or tasks.

For more details on the `dstack run` command, refer to the [Reference](../reference/cli/run.md).

## Ports

A task can expose ports through the `ports` property in `.dstack.yml`, for example, if it is running a web-based app. Here's an example:

<div editor-title="serve.dstack.yml"> 

```yaml
type: task

ports:
  - 7860

commands:
  - pip install -r requirements.txt
  - gradio app.py
```

</div>

When you run it with `dstack run`, by default, `dstack` forwards the traffic 
from the specified port to the same port on your local machine.  

However, you have the option to override the local machine's port for traffic forwarding.

??? info "Port mapping"

    To run the configuration above with traffic available on port `3000` locally, use the following command:

    <div class="termy">

    ```shell
    $ dstack run . -f serve.dstack.yml --port 3000:7860
    ```

    </div>

    Alternatively, instead of using `--port` in the CLI, you can hardcode the local ports directly 
    into the configuration:

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

    Now, even without using `--port` with your `dstack run` command, the traffic will be available on port `3000` 
    on your local machine.

## Environment

By default, `dstack` uses its own Docker images to run tasks, which include pre-configured Python, Conda, and essential
CUDA drivers.

To change the Python version, modify the `python` property in the configuration. Otherwise, `dstack` will use the version
you have locally.

You can install packages using `pip` and `conda` executables from `init`.

If you prefer to use your custom Docker image, use the `image` property in the configuration.

??? info "Build command (experimental)"

    In case you'd like to pre-build the environment rather than install packaged on every run,
    you can use the `build` property. Here's an example:
    
    <div editor-title="train.dstack.yml"> 
    
    ```yaml
    type: task
    
    build:
      - pip install -r requirements.txt
    
    commands:
      - python train.py
    ```
    
    </div>

    To pre-build the environment, you have two options:
    
    _Option 1. Run the `dstack build` command_

    <div class="termy">
    
    ```shell
    $ dstack build . -f train.dstack.yml
    ```
    
    </div>
    
    Similar to the `dstack run` command, `dstack build` also provisions cloud resources and uses them to pre-build the
    environment. Consequently, when running the `dstack run` command again, it will reuse the pre-built image, leading
    to faster startup times, particularly for complex setups.

    _Option 2. Use `--build` with `dstack run`_

    <div class="termy">
    
    ```shell
    $ dstack run . -f train.dstack.yml --build
    ```
    
    </div>

    If there is no pre-built image, the `dstack run` command will build it and upload it to the storage. If the pre-built
    image is already available, the `dstack run` command will reuse it.

## Profiles

If you [configured](projects.md) a project that uses a cloud backend, you can define profiles that specify the
project and the cloud resources to be used.

To configure a profile, simply create the `profiles.yml` file in the `.dstack` folder within your project directory. 
Here's an example:

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gpu-large
    project: gcp
    resources:
       memory: 48GB
       gpu:
         memory: 24GB
    default: true
```

</div>

By default, the `dstack run` command uses the default profile.

!!! info "Multiple profiles"
    You can define multiple profiles according to your needs and use any of them with the `dstack run` command by specifying
    the desired profile using the `--profile` argument.

For more details on the syntax of the `profiles.yml` file, refer to the [Reference](../reference/profiles.yml.md).

## Args

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

## Reload mode

Some web development frameworks like Gradio, Streamlit, and FastAPI support auto-reloading. With `dstack run`, you can
enable the reload mode by using the `--reload` argument.

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml --reload
```

</div>

This feature allows you to run an app in the cloud while continuing to edit the source code locally and have the app
reload changes on the fly.