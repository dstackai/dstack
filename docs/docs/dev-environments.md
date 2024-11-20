# Dev environments

A dev environment lets you provision a remote machine with your code, dependencies, and resources, and access it with
your desktop IDE. 

Dev environments are perfect when you need to run code interactively.

## Define a configuration

First, create a YAML file in your project repo. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are
both acceptable).

<div editor-title="examples/.dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode

python: "3.11"
# Uncomment to use a custom Docker image
#image: dstackai/base:py3.13-0.6-cuda-12.1
ide: vscode

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  gpu: 24GB
```

</div>

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/dev-environment.md) for all the options supported by
    dev environments, along with multiple examples.

## Run a configuration

To run a configuration, use the [`dstack apply`](reference/cli/index.md#dstack-apply) command.

<div class="termy">

```shell
$ dstack apply -f examples/.dstack.yml

 #  BACKEND  REGION    RESOURCES                SPOT  PRICE
 1  runpod   CA-MTL-1  9xCPU, 48GB, A5000:24GB  yes   $0.11
 2  runpod   EU-SE-1   9xCPU, 43GB, A5000:24GB  yes   $0.11
 3  gcp      us-west4  4xCPU, 16GB, L4:24GB     yes   $0.214516

Submit the run vscode? [y/n]: y

Launching `vscode`...
---> 100%

To open in VS Code Desktop, use this link:
  vscode://vscode-remote/ssh-remote+vscode/workflow
```

</div>

`dstack apply` automatically uploads the code from the current repo, including your local uncommitted changes.
To avoid uploading large files, ensure they are listed in `.gitignore`.

### VS Code

To open the dev environment in your desktop IDE, use the link from the output 
(such as `vscode://vscode-remote/ssh-remote+fast-moth-1/workflow`).

![](../assets/images/dstack-vscode-jupyter.png){ width=800 }

### SSH

Alternatively, while the CLI is attached to the run, you can connect to the dev environment via SSH:

<div class="termy">

```shell
$ ssh fast-moth-1
```

</div>

## Manage runs

### List runs

The [`dstack ps`](reference/cli/index.md#dstack-ps)  command lists all running jobs and their statuses. 
Use `--watch` (or `-w`) to monitor the live status of runs.

### Stop a run

Once the run exceeds the [`max_duration`](reference/dstack.yml/dev-environment.md#max_duration), or when you use [`dstack stop`](reference/cli/index.md#dstack-stop), 
the dev environment is stopped. Use `--abort` or `-x` to stop the run abruptly. 

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## Manage fleets

By default, `dstack apply` reuses `idle` instances from one of the existing [fleets](concepts/fleets.md), 
or creates a new fleet through backends.

!!! info "Idle duration"
    To ensure the created fleets are deleted automatically, set
    [`termination_idle_time`](reference/dstack.yml/fleet.md#termination_idle_time).
    By default, it's set to `5min`.

!!! info "Creation policy"
    To ensure `dstack apply` always reuses an existing fleet and doesn't create a new one,
    pass `--reuse` to `dstack apply` (or set [`creation_policy`](reference/dstack.yml/dev-environment.md#creation_policy) to `reuse` in the task configuration).
    The default policy is `reuse_or_create`.

## What's next?

1. Read about [dev environments](dev-environments.md), [tasks](tasks.md), and 
    [services](services.md)
2. See [fleets](concepts/fleets.md) on how to manage fleets

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/dev-environment.md) for all the options supported by
    dev environments, along with multiple examples.
