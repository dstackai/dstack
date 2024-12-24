# Dev environments

A dev environment lets you provision an instance and access it with your desktop IDE.

## Define a configuration

First, define a dev environment configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

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

!!! info "Docker image"
    If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
    pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/dev-environment.md) for all the options supported by
    dev environments, along with multiple examples.

## Run a configuration

To run a dev environment, pass the configuration to [`dstack apply`](reference/cli/dstack/apply.md):

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

`dstack apply` automatically provisions an instance, uploads the contents of the repo (incl. your local uncommitted changes),
and set ups an IDE on the instance.

!!! info "Windows"
    On Windows, `dstack` works both natively and inside WSL. But, for dev environments, 
    it's recommended _not to use_ `dstack apply` _inside WSL_ due to a [VS Code issue :material-arrow-top-right-thin:{ .external }](https://github.com/microsoft/vscode-remote-release/issues/937){:target="_blank"}.

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

The [`dstack ps`](reference/cli/dstack/ps.md)  command lists all running jobs and their statuses. 
Use `--watch` (or `-w`) to monitor the live status of runs.

### Stop a run

A dev environment runs until you stop it or its lifetime exceeds [`max_duration`](reference/dstack.yml/dev-environment.md#max_duration).
To gracefully stop a dev environment, use [`dstack stop`](reference/cli/dstack/stop.md).
Pass `--abort` or `-x` to stop without waiting for a graceful shutdown.

### Attach to a run

By default, `dstack apply` runs in attached mode – it establishes the SSH tunnel to the run, forwards ports, and shows real-time logs.
If you detached from a run, you can reattach to it using [`dstack attach`](reference/cli/dstack/attach.md).

### See run logs

To see the logs of a run without attaching, use [`dstack logs`](reference/cli/dstack/logs.md). 
Pass `--diagnose`/`-d` to `dstack logs` to see the diagnostics logs. It may be useful if a run fails.
For more information on debugging failed runs, see the [troubleshooting](guides/troubleshooting.md) guide.

## Manage fleets

Fleets are groups of cloud instances or SSH machines that you use to run dev environments, tasks, and services.
You can let `dstack apply` provision fleets or [create and manage them directly](concepts/fleets.md).

### Creation policy

By default, when you run `dstack apply` with a dev environment, task, or service,
`dstack` reuses `idle` instances from an existing [fleet](concepts/fleets.md).
If no `idle` instances match the requirements, `dstack` automatically creates a new fleet 
using configured backends.

To ensure `dstack apply` doesn't create a new fleet but reuses an existing one,
pass `-R` (or `--reuse`) to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -R -f examples/.dstack.yml
```

</div>

Alternatively, set [`creation_policy`](reference/dstack.yml/dev-environment.md#creation_policy) to `reuse` in the run configuration.

### Termination policy

If a fleet is created automatically, it remains `idle` for 5 minutes and can be reused within that time.
To change the default idle duration, set
[`termination_idle_time`](reference/dstack.yml/fleet.md#termination_idle_time) in the run configuration (e.g., to 0 or a
longer duration).

!!! info "Fleets"
    For greater control over fleet provisioning, configuration, and lifecycle management, it is recommended to use
    [fleets](concepts/fleets.md) directly.

## What's next?

1. Read about [tasks](tasks.md), [services](services.md), and [repos](concepts/repos.md)
2. Learn how to manage [fleets](concepts/fleets.md)

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/dev-environment.md) for all the options supported by
    dev environments, along with multiple examples.
