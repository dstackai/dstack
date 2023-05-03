# Quick start

## Installation and setup

To use `dstack`, install it with `pip` and start the Hub application.

<div class="termy">

```shell
$ pip install dstack
$ dstack start

The hub is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

!!! info "NOTE:"
    The `dstack start` command starts the Hub application,
    and creates the default project to run workflows locally.

    If you'll want to run workflows in the cloud (e.g. AWS, or GCP), simply log into the Hub application, and 
    create a new project.

## Run your first workflow

Let's proceed and run our first ML workflow.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

!!! info "NOTE:"
    The `dstack init` command initializes the working directory as a `dstack` repository
    and prepares it for use with `dstack`.

Let's define our workflow as follows:

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world!"
```

</div>

!!! info "NOTE:"
    The YAML file allows you to request hardware [resources](usage/resources.md), run [Python](usage/python.md),
    save [artifacts](usage/artifacts.md), use [dependencies](usage/deps.md), create [dev environments](usage/dev-environments.md),
    run [apps](usage/apps.md), and many more.

Go ahead and run the workflow:

<div class="termy">

```shell
$ dstack run hello

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  hello     now        Submitted     
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

</div>

!!! info "NOTE:"
    The `dstack run` command runs the workflow using the settings specified for the project configured with the
    Hub application.

## Create a Hub project

As mentioned above, the default project runs workflows locally.
However, you can log into the application and create other projects that allow you to run workflows in the cloud.

![](../assets/dstack_hub_create_project.png){ width=800 }

If you want the project to use the cloud, you'll need to provide cloud credentials and specify settings such as the
artifact storage bucket and the region where the workflows will run.

![](../assets/dstack_hub_view_project.png){ width=800 }

Once a project is created, copy the CLI command from the project settings and execute it in your terminal.

<div class="termy">

```shell
$ dstack config --url http://127.0.0.1:3000 \
  --project my-awesome-project \
  --token b934d226-e24a-4eab-a284-eb92b353b10f
```

</div>

!!! info "NOTE:"
    The `dstack config` command configures `dstack` to run workflows using the settings from
    the corresponding project.

    You can configure multiple projects and use them interchangeably (by passing the `--project` argument to the `dstack 
    run` command. Any project can be set as the default by passing `--default` to the `dstack config` command.

    Configuring multiple projects can be convenient if you want to run workflows both locally and in the cloud or if 
    you would like to use multiple clouds.


## Manage resources

Consider that you have configured a project that allows you to use a GPU (e.g., a local backend if you have a GPU
locally, or an AWS or GCP backend).

Let's define the following workflow.

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - nvidia-smi
    resources:
      gpu:
        name: V100
        count: 1
```

</div>

Let's run the workflow:

<div class="termy">

```shell
$ dstack run hello

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  hello     now        Submitted     
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

+------------------------------------------------------------------------------+
| NVIDIA-SMI 455.45.01     Driver Version: 455.45.01    CUDA Version: 11.1     |
|--------------------------------+----------------------+----------------------+
| GPU  Name        Persistence-M | Bus-Id        Disp.A | Volatile Uncorr. ECC |
|================================+======================+======================|
|   0  Tesla V100             On | 00000:00:04.0    Off |                    0 |
+--------------------------------+----------------------+----------------------+
```

</div>

If your project is configured to use the cloud, the Hub application will automatically create the necessary cloud
resources to execute the workflow and tear them down once it is finished.

!!! info "NOTE:"
    What's next? Learn how to run [Python](usage/python.md),
    save [artifacts](usage/artifacts.md), use [dependencies](usage/deps.md), request hardware [resources](usage/resources.md), 
    create [dev environments](usage/dev-environments.md), and run [apps](usage/apps.md).

    Also, check our featured [tutorials](../tutorials/dolly.md).