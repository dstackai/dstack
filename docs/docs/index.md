# Getting started

`dstack` makes it very easy for ML engineers to run dev environments, pipelines and apps cost-effectively 
on any cloud.

## Installation and setup

To use `dstack`, install it with `pip` and start the Hub server.

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure]"
$ dstack start

The Hub is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

??? info "What is Hub?"
    Hub is a server that manages projects and users. Each project allows you to configure where to run dev environments,
    pipelines, and apps (e.g. locally or in the cloud), as well as manage users that access it.

    At startup, `dstack` sets up a default project for local execution. To run dev environments, pipelines, and apps in your
    desired cloud account, you must create the corresponding project and configure the `dstack` CLI to use it.

    [Learn more →](guides/projects){ .md-button .md-button--primary }

## Initializing the repo

Before you can run dev environments, pipelines, and apps in any folder,
first have to initialize it as a repo by running the [`dstack init`](reference/cli/init.md) command.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

## Running a dev environment

A dev environment is a virtual machine that includes the environment and an interactive IDE or notebook setup
based on a pre-defined configuration.

Go ahead and define this configuration via YAML (under the `.dstack/workflows` folder).

<div editor-title=".dstack/workflows/dev-environments.yaml"> 

```yaml
workflows:
  - name: code-gpu
    provider: code
    setup:
      - pip install -r dev-environments/requirements.txt
    resources:
      gpu:
        count: 1
```

</div>

[//]: # (TODO [MAJOR]: Currently, it's not convenient to hardcode resources in the YAML and not have a convenient way to switch between projects and resource profiles)

!!! info "NOTE:"
    For dev environments, the configuration allows you to configure hardware resources, 
    set up the Python environment, expose ports, configure cache, and many more. 

    [Learn more →](guides/dev-environments){ .md-button .md-button--primary }

[//]: # (TODO: Currently, it's limited to the built-in VS Code, doesn't forward ports automatically, doesn't provide persistence of the storage, pre-installs packages on every run, and has other limitations)

Now, you can start it using the [`dstack run`](reference/cli/run.md) command:

<div class="termy">

```shell
$ dstack run code-gpu

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  code-gpu  now        Submitted  
 
Starting SSH tunnel...

To exit, press Ctrl+C.

Web UI available at http://127.0.0.1:51845/?tkn=4d9cc05958094ed2996b6832f899fda1
```

</div>

!!! info "NOTE:"
    If you configure a project to run dev environments in the cloud, `dstack` will automatically provision the
    required cloud resources, and forward ports of the dev environment to your local machine. When you stop the 
    dev environment, `dstack` will automatically clean up cloud resources.

## Running a pipeline

A pipeline is a set of pre-defined configurations that allow to process data, train or fine-tune models, do batch inference 
or other tasks.

To run a pipeline, all you have to do is define it via YAML (under the `.dstack/workflows` folder) 
and then run it by name via the CLI.

<div editor-title=".dstack/workflows/pipelines.yaml"> 

```yaml
workflows:
  - name: train-mnist-gpu
    provider: bash
    commands:
      - pip install -r pipelines/requirements.txt
      - python pipelines/train.py
    artifacts:
      - ./lightning_logs
    resources:
      gpu:
        count: 1
```

</div>

!!! info "NOTE:"
    For pipelines, the configuration allows you to configure hardware resources and output artifacts, set up the
    Python environment, expose ports, configure cache, and many more.

    [Learn more →](guides/pipelines){ .md-button .md-button--primary }

[//]: # (TODO: Currently, it's limited to YAML)

Now, you can run the pipeline using the [`dstack run`](reference/cli/run.md) command:

<div class="termy">

```shell
$ dstack run train-mnist-gpu

RUN      WORKFLOW         SUBMITTED  STATUS     TAG
shady-1  train-mnist-gpu  now        Submitted  
 
Provisioning... It may take up to a minute. ✓

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
---> 100%
```

</div>

!!! info "NOTE:"
    If you configure a project to run pipelines in the cloud, the [`dstack run`](reference/cli/run.md) command will automatically provision the 
    required cloud resources.
    After the pipeline is finished, `dstack` will save output artifacts and clean up cloud resources.

## Running an app

An app can be either a web application (such as Streamlit, Gradio, etc.) or an API endpoint (like FastAPI, Flask, etc.)
setup based on a pre-defined configuration.

Go ahead and define this configuration via YAML (under the `.dstack/workflows` folder).

<div editor-title=".dstack/workflows/apps.yaml"> 

```yaml
workflows:
  - name: fastapi-gpu
    provider: bash
    ports:
      - 3000
    commands:
      - pip install -r apps/requirements.txt
      - uvicorn apps.main:app --port 3000 --host 0.0.0.0
    resources:
      gpu:
        count: 1
```

</div>

!!! info "NOTE:"
    For apps, the configuration allows you to customize hardware resources, set up the Python environment, 
    configure cache, and more.

    [Learn more →](guides/apps){ .md-button .md-button--primary }

Now, you can run the app using the [`dstack run`](reference/cli/run.md) command:

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

!!! info "NOTE:"
    If you configure a project to run apps in the cloud, `dstack` will automatically provision the required cloud
    resources, and forward ports of the app to your local machine.

[//]: # (TODO: What's next – Add a link to the Hub guide for the details on how to configure projects)

!!! info "NOTE:"
    Check out the [`dstackai/dstack-examples`](https://github.com/dstackai/dstack-examples/blob/main/README.md) repo for source code and other examples.