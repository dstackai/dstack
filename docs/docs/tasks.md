# Tasks

A task allows you to schedule a job or run a web app. It lets you configure dependencies, resources, ports, and more.
Tasks can be distributed and run on clusters.

Tasks are ideal for training and fine-tuning jobs. They can also be used instead of services if you want to run a web
app but don't need a public endpoint.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `train.dstack.yml`
are both acceptable).

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

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

!!! info "Distributed tasks"
    By default, tasks run on a single instance. However, you can specify
    the [number of nodes](reference/dstack.yml/task.md#distributed-tasks).
    In this case, the task will run a cluster of instances.

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/task.md) for all the options supported by
    tasks, along with multiple examples.

## Run a configuration

To run a configuration, use the [`dstack apply`](reference/cli/index.md#dstack-apply) command.

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

`dstack apply` automatically uploads the code from the current repo, including your local uncommitted changes.
To avoid uploading large files, ensure they are listed in `.gitignore`.

!!! info "Ports"
    If the task specifies [`ports`](reference/dstack.yml/task.md#_ports), `dstack run` automatically forwards them to your
    local machine for convenient and secure access.

!!! info "Queueing tasks"
    By default, if `dstack apply` cannot find capacity, the task fails. 
    To queue the task and wait for capacity, specify the [`retry`](reference/dstack.yml/task.md#queueing-tasks) 
    property in the task configuration.

## Manage runs

### List runs

The [`dstack ps`](reference/cli/index.md#dstack-ps)  command lists all running jobs and their statuses. 
Use `--watch` (or `-w`) to monitor the live status of runs.

### Stop a run

Once the run exceeds the [`max_duration`](reference/dstack.yml/task.md#max_duration), or when you use [`dstack stop`](reference/cli/index.md#dstack-stop), 
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
    pass `--reuse` to `dstack apply` (or set [`creation_policy`](reference/dstack.yml/task.md#creation_policy) to `reuse` in the task configuration).
    The default policy is `reuse_or_create`.

## What's next?

1. Check the [Axolotl](/docs/examples/fine-tuning/axolotl) example
2. Browse [all examples](/examples)
3. See [fleets](concepts/fleets.md) on how to manage fleets

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/task.md) for all the options supported by
    tasks, along with multiple examples.
