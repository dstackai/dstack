# Dev environments

Before submitting a task or deploying a model, you may want to run code interactively.
Dev environments allow you to do exactly that. 

You just specify the required environment, resources, and run it. `dstack` provisions the dev environment
in a configured backend.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are
both acceptable).

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment

# Use either `python` or `image` to configure environment
python: "3.11"

# image: ghcr.io/huggingface/text-generation-inference:latest

ide: vscode

# (Optional) Configure `gpu`, `memory`, `disk`, etc
resources:
  gpu: 80GB
```

</div>

The YAML file allows you to specify your own Docker image, environment variables, 
resource requirements, etc.
If image is not specified, `dstack` uses its own (pre-configured with Python, Conda, and essential CUDA drivers).

For more details on the file syntax, refer to [`.dstack.yml`](../reference/dstack.yml.md).

## Run the configuration

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

When `dstack` provisions the dev environment, it uses the current folder contents.

!!! info "Exclude files"
    If there are large files or folders you'd like to avoid uploading, 
    you can list them in either `.gitignore` or `.dstackignore`.

### IDE

To open the dev environment in your desktop IDE, use the link from the output 
(such as `vscode://vscode-remote/ssh-remote+fast-moth-1/workflow`).

![](../../assets/images/dstack-vscode-jupyter.png){ width=800 }

### SSH

Alternatively, you can connect to the dev environment via SSH:

<div class="termy">

```shell
$ ssh fast-moth-1
```

</div>

## Configure policies

For a run, multiple policies can be configured, such as spot policy, retry policy, max duration, max price, etc.

Policies can be configured either via [`dstack run`](../reference/cli/index.md#dstack-run)
or [`.dstack/profiles.yml`](../reference/profiles.yml.md).
For more details on policies and their defaults, refer to [`.dstack/profiles.yml`](../reference/profiles.yml.md).

## Manage runs

### Stop a run

Once the run exceeds the max duration,
or when you use [`dstack stop`](../reference/cli/index.md#dstack-stop), 
the dev environment and its cloud resources are deleted.

### List runs 

The [`dstack ps`](../reference/cli/index.md#dstack-ps) command lists all running runs and their status.

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## What's next?

1. Check out [`.dstack.yml`](../reference/dstack.yml.md), [`dstack run`](../reference/cli/index.md#dstack-run),
    and [`profiles.yml`](../reference/profiles.yml.md)
2. Read about [tasks](tasks.md), [services](tasks.md), and [pools](pools.md)