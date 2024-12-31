# Tasks

A task allows you to run arbitrary commands on one or more nodes.
They are best suited for one-off jobs like training or batch processing,
but can also be used for serving apps if features supported by [services](`services.md`) are not required.

## Define a configuration

First, define a task configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

[//]: # (TODO: Make tabs - single machine & distributed tasks & web app)

<div editor-title="examples/fine-tuning/axolotl/train.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: axolotl-train

# Using the official Axolotl's Docker image
image: winglian/axolotl-cloud:main-20240429-py3.11-cu121-2.2.1

# Required environment variables
env:
  - HF_TOKEN
  - WANDB_API_KEY
# Commands of the task
commands:
  - accelerate launch -m axolotl.cli.train examples/fine-tuning/axolotl/config.yaml

resources:
  gpu:
    # 24GB or more vRAM
    memory: 24GB..
    # Two or more GPU
    count: 2..
```

</div>

!!! info "Docker image"
    If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
    pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Distributed tasks"
    By default, tasks run on a single instance. However, you can specify
    the [number of nodes](../reference/dstack.yml/task.md#distributed-tasks).
    In this case, the task will run on a cluster of instances.

!!! info "Reference"
    See [.dstack.yml](../reference/dstack.yml/task.md) for all the options supported by
    tasks, along with multiple examples.

## Run a configuration

To run a task, pass the configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ HF_TOKEN=...
$ WANDB_API_KEY=...
$ dstack apply -f examples/.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:3  yes   $0.33

Submit the run axolotl-train? [y/n]: y

Launching `axolotl-train`...
---> 100%

{'loss': 1.4967, 'grad_norm': 1.2734375, 'learning_rate': 1.0000000000000002e-06, 'epoch': 0.0}
  0% 1/24680 [00:13<95:34:17, 13.94s/it]
  6% 73/1300 [00:48<13:57,  1.47it/s]
```

</div>

`dstack apply` automatically provisions instances, uploads the contents of the repo (incl. your local uncommitted changes),
and runs the commands.

!!! info "Ports"
    If the task specifies [`ports`](../reference/dstack.yml/task.md#_ports), `dstack apply` automatically forwards them to your
    local machine for convenient and secure access.

!!! info "Queueing tasks"
    By default, if `dstack apply` cannot find capacity, the task fails. 
    To queue the task and wait for capacity, specify the [`retry`](../reference/dstack.yml/task.md#queueing-tasks) 
    property in the task configuration.

## Manage runs

### List runs

The [`dstack ps`](../reference/cli/dstack/ps.md)  command lists all running jobs and their statuses. 
Use `--watch` (or `-w`) to monitor the live status of runs.

### Stop a run

A task runs until it's completed or its lifetime exceeds [`max_duration`](../reference/dstack.yml/dev-environment.md#max_duration).
You can also gracefully stop a task using [`dstack stop`](../reference/cli/dstack/stop.md).
Pass `--abort` or `-x` to stop without waiting for a graceful shutdown.

### Attach to a run

By default, `dstack apply` runs in attached mode – it establishes the SSH tunnel to the run, forwards ports, and shows real-time logs.
If you detached from a run, you can reattach to it using [`dstack attach`](../reference/cli/dstack/attach.md).

### See run logs

To see the logs of a run without attaching, use [`dstack logs`](../reference/cli/dstack/logs.md).
Pass `--diagnose`/`-d` to `dstack logs` to see the diagnostics logs. It may be useful if a run fails.
For more information on debugging failed runs, see the [troubleshooting](../guides/troubleshooting.md) guide.

## Manage fleets

Fleets are groups of cloud instances or SSH machines that you use to run dev environments, tasks, and services.
You can let `dstack apply` provision fleets or [create and manage them directly](fleets.md).

### Creation policy

By default, when you run `dstack apply` with a dev environment, task, or service,
`dstack` reuses `idle` instances from an existing [fleet](fleets.md).
If no `idle` instances match the requirements, `dstack` automatically creates a new fleet 
using configured backends.

To ensure `dstack apply` doesn't create a new fleet but reuses an existing one,
pass `-R` (or `--reuse`) to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -R -f examples/.dstack.yml
```

</div>

Alternatively, set [`creation_policy`](../reference/dstack.yml/dev-environment.md#creation_policy) to `reuse` in the run configuration.

### Termination policy

If a fleet is created automatically, it remains `idle` for 5 minutes and can be reused within that time.
To change the default idle duration, set
[`termination_idle_time`](../reference/dstack.yml/fleet.md#termination_idle_time) in the run configuration (e.g., to 0 or a
longer duration).

!!! info "Fleets"
    For greater control over fleet provisioning, configuration, and lifecycle management, it is recommended to use
    [fleets](fleets.md) directly.

## What's next?

1. Read about [dev environments](dev-environments.md), [services](services.md), and [repos](repos.md)
2. Learn how to manage [fleets](fleets.md)
3. Check the [Axolotl](/examples/fine-tuning/axolotl) example

!!! info "Reference"
    See [.dstack.yml](../reference/dstack.yml/task.md) for all the options supported by
    tasks, along with multiple examples.
