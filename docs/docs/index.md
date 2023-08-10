# Quickstart

`dstack` is an open-source tool that streamlines LLM development and deployment across multiple clouds.

## Installation

To use `dstack`, install it with `pip`, and start the server.

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure,lambda]"
$ dstack start

The server is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

!!! info "Projects"
    On startup, the server sets up a default project that runs everything locally. 
    To run workloads in your cloud, log into the UI, create the corresponding project, 
    and [configure](projects.md) the CLI to use it.

## Initialization

To use `dstack` for your project, make sure to first run the [`dstack init`](reference/cli/init.md) command in the root folder of the project.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

## Configuration files

A configuration is a YAML file that describes what you want to run with `dstack`. Configurations can be of three
types: `dev-environment`, `task`, and `service`.

### Dev environments

A dev environment is a virtual machine pre-configured an IDE.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

init:
  - pip install -r requirements.txt

ide: vscode
```

</div>

Once it's live, you can open it in your local VS Code by clicking the provided URL in the output.

### Tasks

A task can be any script that you may want to run on demand: a batch job, or a web application.

<div editor-title="serve.dstack.yml"> 

```yaml
type: task

ports:
  - 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

</div>

While the task runs in the cloud, the CLI forwards traffic, allowing you to access the application from your local
machine. 

### Services

A service is an application that is accessible through a public endpoint.

<div editor-title="deploy.dstack.yml"> 

```yaml
type: service

gateway: ${{ secrets.GATEWAY_ADDRESS }}

port: 7860

commands:
  - pip install -r requirements.txt
  - python app.py
```

</div>

Once the service is up, `dstack` makes it accessible from the Internet through
the [gateway](guides/services.md#configuring-a-gateway).

[//]: # (!!! info "Configuration filename")
[//]: # (    The configuration file must be named with the suffix `.dstack.yml`. For example,)
[//]: # (    you can name the configuration file `.dstack.yml` or `serve.dstack.yml`. You can define)
[//]: # (    these configurations anywhere within your project. )
[//]: # (    )
[//]: # (    Each folder may have one default configuration file named `.dstack.yml`.)

For more details on the syntax of configuration file, refer to the [`.dstack.yml` Reference](../docs/reference/dstack.yml/index.md).

## Running

### Default configuration

To run a configuration, you have to call the [`dstack run`](reference/cli/run.md) command and pass the path to the 
directory which you want to use as a working directory when running the configuration.

<div class="termy">

```shell
$ dstack run . 

 RUN          CONFIGURATION  USER   PROJECT  INSTANCE  RESOURCES        SPOT
 fast-moth-1  .dstack.yml    admin  local    -         5xCPUs, 15987MB  auto  


Provisioning and starting SSH tunnel...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+fast-moth-1/workflow

To exit, press Ctrl+C.
```

</div>

If you've not specified a specific configuration file, `dstack` will use the default configuration
defined in the given directory (named `.dstack.yml`).

### Non-default configuration

If you want to run a non-default configuration, you have to specify the path to the configuration
using the `-f` argument:

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml

 RUN             CONFIGURATION   USER   PROJECT  INSTANCE  RESOURCES        SPOT
 old-lionfish-1  serve.dstack.yml  admin  local    -         5xCPUs, 15987MB  auto  

Provisioning and starting SSH tunnel...
---> 100%

To stop, press Ctrl+C.

Launching in *reload mode* on: http://127.0.0.1:7860 (Press CTRL+C to quit)
```

</div>

!!! info "Port forwarding"
    By default, `dstack` forwards the ports used by dev environments and tasks to your local machine for convenient access.

??? info ".gitignore"
    When running dev environments or tasks, `dstack` uses the exact version of code that is present in the folder where you
    use the `dstack run` command.

    If your folder has large files or folders, this may affect the performance of the `dstack run` command. To avoid this,
    make sure to create a `.gitignore` file and include these large files or folders that you don't want to include when
    running dev environments or tasks.

For more details on how the `dstack run` command works, refer to the [CLI Reference](reference/cli/run.md).

## Profiles

If you have [configured](projects.md) a project that runs dev environments and tasks in the cloud, you can define multiple
profiles. Each profile can configure the project to use and the resources required for the run.

To define profiles, create the `profiles.yml` file in the `.dstack` folder within your project directory. Here's an example:

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-t4
    project: gcp
    
    resources:
      memory: 24GB
      gpu:
        name: T4
        
    spot_policy: auto
    retry_policy:
      limit: 30min
    max_duration: 1d
      
    default: true
```

</div>

!!! info "Spot instances"
    If `spot_policy` is set to `auto`, `dstack` prioritizes spot instances.
    If these are unavailable, it uses `on-demand` instances. To cut costs, set `spot_policy` to `spot`.
    
    If `dstack` can't find capacity, an error displays. To enable continuous capacity search, use `retry_policy` with a 
    `limit`. For example, setting it to `30min` makes `dstack` search for capacity for 30 minutes.

    Note that spot instances are significantly cheaper but can be interrupted. Your code should ideally 
    handle interruptions and resume work from saved checkpoints.

Now, if you use the `dstack run` command, `dstack` will use the default profile.

!!! info "Multiple profiles"
    You can define multiple profiles according to your needs and use any of them with the `dstack run` command by specifying
    the desired profile using the `--profile` argument.

For more details on the syntax of the `profiles.yml` file, refer to the [Reference](reference/profiles.yml.md).