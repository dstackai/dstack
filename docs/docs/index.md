# Introduction

`dstack` makes it very easy for ML teams to automate running dev environments and tasks in their cloud.

## Installation

To use `dstack`, install it with `pip`, and start the server.

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure]"
$ dstack start

The server is available at http://127.0.0.1:3000?token=b934d226-e24a-4eab-eb92b353b10f
```

</div>

On startup, the server sets up a default project that runs everything locally. 

!!! info "Projects"

    To run dev environments and tasks in your cloud, log into the UI, create the corresponding project, 
    and [configure](guides/projects) the CLI to use it.

## Initialization

To use `dstack` for your project, make sure to first run the [`dstack init`](reference/cli/init.md) command in the root folder of the project.

<div class="termy">

```shell
$ mkdir quickstart && cd quickstart
$ dstack init
```

</div>

## Configurations

A configuration is a YAML file that describes what you want to run with `dstack`. Configurations can be of two
types: `dev-environment` and `task`.

### Dev environments

Here's an example of a `dev-environment` configuration:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
ide: vscode
```

</div>

This configuration runs a dev environment with a pre-built environment to which you can connect via VS Code Desktop.

### Tasks

Here's an example of a `task` configuration:

<div editor-title="app.dstack.yml"> 

```yaml
type: task
ports:
  - 7860
commands:
  - pip install -r requirements.txt
  - gradio app.py
```

</div>

A task can be either a batch job, such as training or fine-tuning a model, or a web application.

!!! info "Configuration filename"
    The configuration file must be named with the suffix `.dstack.yml`. For example,
    you can name the configuration file `.dstack.yml` or `app.dstack.yml`. You can define
    these configurations anywhere within your project. 
    
    Each folder may have one default configuration file named `.dstack.yml`.

[//]: # (TODO: Mention pre-built)

For more details on the syntax of configuration file, refer to the [`.dstack.yml` Reference](reference/dstack.yaml.md).

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
$ dstack run . -f app.dstack.yml

 RUN             CONFIGURATION   USER   PROJECT  INSTANCE  RESOURCES        SPOT
 old-lionfish-1  app.dstack.yml  admin  local    -         5xCPUs, 15987MB  auto  

Provisioning and starting SSH tunnel...
---> 100%

To stop, press Ctrl+C.

Launching in *reload mode* on: http://127.0.0.1:7860 (Press CTRL+C to quit)
```

</div>

!!! info "Port forwarding"
    By default, `dstack` forwards the ports used by dev environments and tasks to your local machine for convenient access.

??? info "Using .gitignore"
    When running dev environments or tasks, `dstack` uses the exact version of code that is present in the folder where you
    use the `dstack run` command.

    If your folder has large files or folders, this may affect the performance of the `dstack run` command. To avoid this,
    make sure to create a `.gitignore` file and include these large files or folders that you don't want to include when
    running dev environments or tasks.

For more details on how the `dstack run` command works, refer to the [CLI Reference](reference/cli/run.md).

## Profiles

If you have [configured](guides/projects.md) a project that runs dev environments and tasks in the cloud, you can define multiple
profiles. Each profile can configure the project to use and the resources required for the run.

To define profiles, create the `profiles.yml` file in the `.dstack` folder within your project directory. Here's an example:

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

Now, if you use the `dstack run` command, `dstack` will use the default profile.

!!! info "Multiple profiles"
    You can define multiple profiles according to your needs and use any of them with the `dstack run` command by specifying
    the desired profile using the `--profile` argument.

For more details on the syntax of the `profiles.yml` file, refer to the [`profiles.yml` Reference](reference/profiles.yml.md).