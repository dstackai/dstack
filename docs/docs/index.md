# Quick start

`dstack` helps ML engineers define dev environments, pipelines, and apps as code and run them cost-effectively with a single command, 
either locally or in any cloud account of their choice.

## Installation and setup

To use `dstack`, install it with `pip` and start the Hub server.

<div class="termy">

```shell
$ pip install dstack
$ dstack start

The Hub is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

??? info "What is Hub?"
    Hub is a server application designed to facilitate team collaboration and streamline the usage of `dstack`. 
    It orchestrates runs, stores cloud credentials, tracks usage, and performs other essential functions.

    You have the flexibility to start Hub locally, on a dedicated server, or in the cloud. When starting it locally, 
    the default project is automatically configured to run everything locally. If Hub is started remotely, you can 
    configure the CLI to connect to a remote Hub using the `dstack config` command.

    To enable Hub to run dev environments, pipelines, and apps in your preferred cloud account (AWS, GCP, etc), you need to 
    log in to Hub, configure the corresponding project, and provide the necessary cloud credentials.

## Init the repo

A repo is any folder from which you can run dev environments, pipelines, and apps.

To initialize a folder as a repo, you have to run the `dstack init` command there.

<div class="termy">

```shell
$ mkdir hello-dstack && cd hello-dstack
$ dstack init
```

</div>

## Run your first dev environment

To create a dev environment, all you have to do is define it via YAML (under the `.dstack/workflows` folder) 
and then run it by name via the CLI.

<div editor-title=".dstack/workflows/hello-env.yaml"> 

```yaml
workflows:
  - name: hello-env
    provider: code
    python: 3.10
    setup:
      - pip install transformers accelerate gradio
    resources:
      gpu:
        name: V100
        count: 1
```

</div>

!!! info "NOTE:"
    The YAML file support multiple providers and allows you to configure hardware resources, 
    set up the Python environment, expose ports, configure cache, and many more.

[//]: # (TODO: Currently, it's limited to the built-in VS Code, doesn't forward ports automatically, doesn't provide persistence of the storage, pre-installs packages on every run, and has other limitations)

Now, you can run the dev environment at any time using the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello-env

RUN      WORKFLOW   SUBMITTED  STATUS     TAG
shady-1  hello-env  now        Submitted  
 
Starting SSH tunnel...

To exit, press Ctrl+C.

Web UI available at http://127.0.0.1:51845/?tkn=4d9cc05958094ed2996b6832f899fda1
```

</div>

`dstack` launches the dev environment based on the configuration and fetches there an exact copy of the source code
that is present in the folder where you run the `dstack` command.

[//]: # (TODO: A screenshot)

!!! info "NOTE:"
    If you configure a project to run dev environments in the cloud, `dstack` will automatically provision the
    required cloud resources, and forward ports of the dev environment to your local machine. When you stop the 
    dev environment, `dstack` will automatically clean up the cloud resources.

## Run your first pipeline

Pipelines allow to process data, train or fine-tune models, do batch inference or any other tasks
based on a pre-defined configuration.

To run a pipeline, all you have to do is define it via YAML (under the `.dstack/workflows` folder) 
and then run it by name via the CLI.

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
```

</div>

!!! info "NOTE:"
    The YAML file support multiple providers and allows you to configure hardware resources and output artifacts, set up the
    Python environment, expose ports, configure cache, and many more.

[//]: # (TODO: Currently, it's limited to YAML)

Now, you can run the pipeline using the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  hello     now        Submitted  
 
Provisioning... It may take up to a min.

To exit, press Ctrl+C.

Hello, world!
```

</div>

When running, the pipeline uses the exact copy of the source code that is locally present in the folder where you run
the `dstack` command.

!!! info "NOTE:"
    If you configure a project to run pipelines in the cloud, the `dstack run` command will automatically provision the 
    required cloud resources.
    After the pipeline is finished, `dstack` will automatically save output artifacts and clean up the cloud resources.

[//]: # (TODO: What's next – Add a link to the Hub guide for the details on how to configure projects)