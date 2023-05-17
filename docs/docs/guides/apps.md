# Apps

An app can be either a web application (such as Streamlit, Gradio, etc.) or an API endpoint (like FastAPI, Flask, etc.)
setup based on a pre-defined configuration.

With `dstack`, you can define such configurations as code and run your apps with a single command, either
locally or in any cloud.

## Creating a configuration file

A configuration can be defined as a YAML file (under the `.dstack/workflows` directory).

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello-fastapi
    provider: bash
    ports: 1
    commands:
      - pip install fastapi uvicorn
      - uvicorn main:app --port $PORT_0 --host 0.0.0.0
```

</div>

The configuration allows you to customize hardware resources, set up the Python environment, 
and more.

To configure ports, you have to specify the number of ports via the `ports` property. They'll be
passed to the run as environment variables like `PORT_0`, `PORT_1`, etc.

[//]: # (TODO [MAJOR]: It supports only YAML and doesn't allow to use pure Python)

[//]: # (TODO [MAJOR]: It's not convenient to use dstack environment variables for ports)

[//]: # (TODO [MAJOR]: Currently, it requires the user to hardcode `--host 0.0.0.0`)

## Running an app

Once a configuration is defined, you can run it using the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  hello     now        Submitted  
 
Provisioning... It may take up to a minute. ✓

To exit, press Ctrl+C.

Hello, world!
```

</div>

For convenience, `dstack` uses an exact copy of the source code that is locally present in the folder where you use the `dstack` command.

??? info "Using .gitignore"
    If you don't want the app to sync certain files (especially large local files that are not needed
    for the app), feel free to add them to the `.gitignore` file. In this case, `dstack` will ignore them,
    even if you aren't using Git.

If you configure a project to run dev environments in the cloud, `dstack` will automatically provision the
required cloud resources, and forward ports of the dev environment to your local machine.

??? info "Configuring projects"
    The default project runs apps locally. However, you can
    log into Hub and configure additional projects to run apps in a cloud account of your choice. 

    You can configure multiple projects and pass the project name to the CLI by using the `--project` argument.

#### Stopping a run

To stop the run, click `Ctrl`+`C` while the `dstack run` command is running,
or use the `dstack stop` command. `dstack` will automatically save the output artifacts and clean up any cloud resources 
if they are used.

## Configuring hardware resources

If your project is configured to run apps in the cloud, you can use the `resources` property in the YAML file to 
request hardware resources like memory, GPUs, and shared memory size.

Additionally, you can choose whether dstack should use interruptible instances (also known as spot instances).

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world!"
    resources:
      gpu:
        name: V100
        count: 1
      interruptible: true
```

</div>

## Setting up the environment

You can use `pip` and `conda` executables to install packages and set up the environment.

Use the `python` property to specify a version of Python for pre-installation. Otherwise, `dstack` uses the local version.

[//]: # (TODO [MAJOR]: Currently, there is no way to pre-build the environment)

#### Using Docker

To run the app with your custom Docker image, you can use the `docker` provider.

<div editor-title=".dstack/workflows/hello-docker.yaml"> 

```yaml
workflows:
  - name: hello-fastapi
    provider: python:3.11
    ports: 1
    commands:
      - pip install fastapi uvicorn
      - uvicorn main:app --port $PORT_0 --host 0.0.0.0
```

</div>

## Configuring cache

Your app may download files like pre-trained models, external data, or Python
packages. To avoid downloading them on each run, you can choose
which paths to cache between runs. 

<div editor-title=".dstack/workflows/hello-cache.yaml"> 

```yaml
workflows:
  - name: hello-cache
    provider: bash
    commands:
      - pip install torchvision
      - pip list | grep torchvision
    cache:
      - ~/.cache/pip
```

</div>

!!! info "NOTE:"
    Cache saves files in its own storage and downloads them at startup. This improves performance and saves you 
    from data transfer costs.

#### Cleaning up the cache

To clean up the cache, use the `dstack prune cache` CLI command, followed by the name of the configuration.