# Apps

An app can be either a web application (such as Streamlit, Gradio, etc.) or an API endpoint (like FastAPI, Flask, etc.)
setup based on a pre-defined configuration.

With `dstack`, you can define such configurations as code and run your apps with a single command, either
locally or in any cloud.

## Creating a configuration file

A configuration can be defined as a YAML file (under the `.dstack/workflows` directory).

<div editor-title=".dstack/workflows/apps.yaml"> 

```yaml
workflows:
  - name: fastapi-gpu
    provider: bash
    ports: 1
    commands:
      - pip install -r apps/requirements.txt
      - uvicorn apps.main:app --port $PORT_0 --host 0.0.0.0
    resources:
      gpu:
        count: 1
```

</div>

The [configuration](../reference/providers/bash.md) allows you to customize hardware resources, set up the Python environment, 
and more.

To configure ports, you have to specify the number of ports via the 
[`ports`](../reference/providers/bash.md#ports) property. They'll be
passed to the run as environment variables like `PORT_0`, `PORT_1`, etc.

[//]: # (TODO [MEDIUM]: It doesn't explain how to mount deps)

[//]: # (TODO [MAJOR]: It supports only YAML and doesn't allow to use pure Python)

[//]: # (TODO [MAJOR]: It's not convenient to use dstack environment variables for ports)

[//]: # (TODO [MAJOR]: Currently, it requires the user to hardcode `--host 0.0.0.0`)

## Running an app

Once a configuration is defined, you can run it using the [`dstack run`](../reference/cli/run.md) command:

<div class="termy">

```shell
$ dstack run fastapi-gpu
 RUN           WORKFLOW     SUBMITTED  STATUS     TAG
 silly-dodo-1  fastapi-gpu  now        Submitted     

Starting SSH tunnel...

To interrupt, press Ctrl+C.

INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:63475 (Press CTRL+C to quit)
```

</div>

For convenience, `dstack` uses an exact copy of the source code that is locally present in the folder where you use the `dstack` command.

??? info "Using .gitignore"
    If you don't want the app to sync certain files (especially large local files that are not needed
    for the app), feel free to add them to the `.gitignore` file. In this case, `dstack` will ignore them,
    even if you aren't using Git.

If you configure a project to run apps in the cloud, `dstack` will automatically provision the
required cloud resources, and forward ports of the app to your local machine.

??? info "Projects"
    The default project runs apps locally. However, you can
    log into Hub and configure additional projects to run apps in a cloud account of your choice. 

    [Learn more →](guides/dev-environments){ .md-button .md-button--primary }

#### Stopping a run

To stop the app, click `Ctrl`+`C` while the [`dstack run`](../reference/cli/run.md) command is running,
or use the [`dstack stop`](../reference/cli/stop.md) command. `dstack` will automatically clean up any cloud resources 
if they are used.

## Configuring resources

If your project is configured to run apps in the cloud, you can use the 
[`resources`](../reference/providers/bash.md#resources) property in the YAML file to 
request hardware resources like memory, GPUs, and shared memory size.

<div editor-title=".dstack/workflows/apps.yaml"> 

```yaml
workflows:
  - name: fastapi-gpu-i
    provider: bash
    ports: 1
    commands:
      - pip install -r apps/requirements.txt
      - uvicorn apps.main:app --port $PORT_0 --host 0.0.0.0
    resources:
      gpu:
        count: 1
      interruptible: true
```

</div>

The [`interruptible`](../reference/providers/bash.md#resources) property tells `dstack` to utilize spot instances. Spot instances may be not always available.
But when they are available, they are significantly cheaper.

[//]: # (TODO [MEDIUM]: It doesn't allow to switch to on-demand automatically)

## Setting up the environment

You can use `pip` and `conda` executables to install packages and set up the environment.

Use the [`python`](../reference/providers/bash.md) property to specify a version of Python for pre-installation. Otherwise, `dstack` uses the local version.

[//]: # (TODO [MAJOR]: Currently, there is no way to pre-build the environment)

#### Using Docker

To run the app with your custom Docker image, you can use the `docker` provider.

<div editor-title=".dstack/workflows/apps.yaml"> 

```yaml
workflows:
  - name: fastapi-docker
    provider: docker
    image: python:3.11
    ports: 1
    commands:
      - pip install -r apps/requirements.txt
      - uvicorn apps.main:app --port $PORT_0 --host 0.0.0.0
```

</div>

## Configuring cache

Apps may download files like pre-trained models, external data, or Python
packages. To avoid downloading them on each run, you can choose
which paths to cache between runs. 

<div editor-title=".dstack/workflows/apps.yaml"> 

```yaml
workflows:
  - name: fastapi-cached
    provider: bash
    ports: 1
    commands:
      - pip install -r apps/requirements.txt
      - uvicorn apps.main:app --port $PORT_0 --host 0.0.0.0
    cache:
      - path: ~/.cache/pip
```

</div>

!!! info "NOTE:"
    Cache saves files in the configured storage and downloads them at startup. This improves performance and saves you 
    from data transfer costs.

#### Cleaning up the cache

To clean up the cache, use the [`dstack prune cache`](../reference/cli/prune.md) CLI command, followed by the name of the configuration.

!!! info "NOTE:"
    Check out the [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples/blob/main/README.md) repo for source code and other examples.

[//]: # (TODO [TASK]: Mention secrets)