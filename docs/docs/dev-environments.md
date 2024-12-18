# Dev environments

A dev environment lets you provision an instance and access it with your desktop IDE.

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

To run a configuration, use the [`dstack apply`](reference/cli/dstack/apply.md) command.

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

!!! info "Windows"
    On Windows, `dstack` works both natively and inside WSL. But, for dev environments, 
    it's recommended _not to use_ `dstack apply` _inside WSL_ due to a [VS Code issue :material-arrow-top-right-thin:{ .external }](https://github.com/microsoft/vscode-remote-release/issues/937){:target="_blank"}.

`dstack apply` automatically provisions an instance, uploads the contents of the repo (incl. your local uncommitted changes),
and runs the configuration.

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

Once the run exceeds the [`max_duration`](reference/dstack.yml/dev-environment.md#max_duration), or when you use [`dstack stop`](reference/cli/dstack/stop.md), 
the dev environment is stopped. Use `--abort` or `-x` to stop the run abruptly. 

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## Manage fleets

### Creation policy

By default, when you run `dstack apply` with a dev environment, task, or service,
`dstack` reuses `idle` instances from an existing [fleet](concepts/fleets.md).
If no `idle` instances matching the requirements, it automatically creates a new fleet 
using backends.

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
