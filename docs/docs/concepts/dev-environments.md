# Dev environments

Before scheduling a task or deploying a model, you may want to run code interactively. Dev environments allow you to
provision a remote machine set up with your code and favorite IDE with just one command.

## Configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are
both acceptable).

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

# Specify the Python version, or your Docker image
python: "3.11"

# This pre-configures the IDE with required extensions
ide: vscode

# Specify GPU, disk, and other resource requirements
resources:
  gpu: 80GB
```

</div>

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

> See the [.dstack.yml reference](../reference/dstack.yml/dev-environment.md)
> for many examples on dev envioronment configuration.

## Running

To run a configuration, use the [`dstack run`](../reference/cli/index.md#dstack-run) command followed by the working directory path, 
configuration file path, and other options.

<div class="termy">

```shell
$ dstack run . -f .dstack.yml

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y

Provisioning `fast-moth-1`...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+fast-moth-1/workflow
```

</div>

When `dstack` provisions the dev environment, it mounts the project folder contents.

!!! info ".gitignore"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in `.gitignore`.

> See the [CLI reference](../reference/cli/index.md#dstack-run) for more details
> on how `dstack run` works.

### VS Code

To open the dev environment in your desktop IDE, use the link from the output 
(such as `vscode://vscode-remote/ssh-remote+fast-moth-1/workflow`).

![](../../assets/images/dstack-vscode-jupyter.png){ width=800 }

### SSH

Alternatively, while the CLI is attached to the run, you can connect to the dev environment via SSH:

<div class="termy">

```shell
$ ssh fast-moth-1
```

</div>

## Managing runs

**Stopping runs**

Once the run exceeds the max duration,
or when you use [`dstack stop`](../reference/cli/index.md#dstack-stop), 
the dev environment and its cloud resources are deleted.

**Listing runs**

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## What's next?

1. Check the [`.dstack.yml` reference](../reference/dstack.yml/dev-environment.md) for more details and examples