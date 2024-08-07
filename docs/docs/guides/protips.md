# Protips

Below are tips and tricks to use `dstack` more efficiently.

## Fleets

By default, when running dev environments, tasks, or services, `dstack apply` reuses `idle` 
instances from existing fleets. If no `idle` instances match the requirements, it creates a new fleet automatically.

To avoid creating new fleet automatically, 
set [ `creation_policy`](reference/dstack.yml/dev-environment.md#creation_policy) to `reuse` in the configuration.

> Use [fleets](../fleets.md) configurations to create fleets manually. This reduces startup time for dev environments,
> tasks, and services, and is very convenient if you want to reuse fleets across runs.

## Dev environments

Before running a task or service, it's recommended that you first start with a dev environment. Dev environments
allow you to run commands interactively.

Once the commands work, go ahead and run them as a task or a service.

??? info "Notebooks"
    **VS Code**
    
    When you access a dev environment using your desktop VS Code, it allows you to work with Jupyter notebooks via its
    pre-configured and easy-to-use extension.

    **JupyterLab**

    If you prefer to use JupyterLab, you can run it as a task:

    ```yaml
    type: task
    
    commands:
        - pip install jupyterlab
        - jupyter lab --allow-root
    
    ports:
        - 8888
    
    ```

## Tasks vs. services

Tasks can be used not only for batch jobs but also for web applications.

<div editor-title="app.dstack.yml">

```yaml
type: task
name: streamlit-task

python: "3.10"

commands:
  - pip3 install streamlit
  - streamlit hello
ports: 
  - 8501

```

</div>

While you run a task, `dstack apply` forwards the remote ports to `localhost`.

<div class="termy">

```shell
$ dstack apply -f app.dstack.yml

  Welcome to Streamlit. Check out our demo in your browser.

  Local URL: http://localhost:8501
```

</div>

This allows you to access the remote `8501` port on `localhost:8501` while the CLI is attached.

??? info "Port mapping"
    If you want to override the local port, use the `--port` option:
        
    <div class="termy">
    
    ```shell
    $ dstack apply -f app.dstack.yml --port 3000:8501
    ```
    
    </div>
    
    This will forward the remote `8501` port to `localhost:3000`.

[Services](../services.md) require a gateway but they also provide additional features for
production-grade service deployment not offered by tasks, such as HTTPS domains and auto-scaling.
If you run a web app as a task and it works, go ahead and run it as a service.

## Environment variables

If a configuration requires an environment variable that you don't want to hardcode in the YAML, you can define it
without assigning a value:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: vscode

python: "3.10"

env:
  - HUGGING_FACE_HUB_TOKEN
ide: vscode
```

</div>

Then, you can pass the environment variable either via the shell:

```shell
HUGGING_FACE_HUB_TOKEN=... dstack apply -f .dstack.yml
```

Or via the `-e` option of the `dstack apply` command:

```shell
dstack apply -f .dstack.yml -e HUGGING_FACE_HUB_TOKEN=...
```

??? info ".env"
    A better way to configure environment variables not hardcoded in YAML is by specifying them in a `.env` file:

    ```
    HUGGING_FACE_HUB_TOKEN=...
    ```
    
    If you install [`direnv` :material-arrow-top-right-thin:{ .external }](https://direnv.net/){:target="_blank"},
    it will automatically pass the environment variables from the `.env` file to the `dstack apply` command.

    Remember to add `.env` to `.gitignore` to avoid pushing it to the repo.    

## Data and models

`dstack` has support for [volumes](../concepts/volumes.md)
to persist data across different runs and instance interruptions.
Volumes are ideal for storing intermediate work and data that should be quickly accessible.

You can also load and save data using an object storage like S3 or HuggingFace Datasets.
For models, it's best to use services like HuggingFace Hub.
`dstack` has no explicit support for object storage.
You can load and save data directly from your code.

## Idle duration

If you run a dev environment, task, or service via `dstack apply`,
and it creates a new fleet, it sets the idle duration to `5m`. If instances of the fleet are `idle`
for this time, `dstack` terminates them.

If you create a fleet manually, the idle duration is not set.

> You can override idle duration for fleets, dev environment, tasks, and services by
> setting [`termination_idle_duration`](../reference/dstack.yml/dev-environment.md#termination_idle_duration) in the configuration file. 

[//]: # (## Profiles)
[//]: # ()
[//]: # (If you don't want to specify the same parameters for each configuration, you can define them once via [profiles]&#40;../reference/profiles.yml.md&#41;)
[//]: # (and reuse them across configurations.)
[//]: # ()
[//]: # (This can be handy, for example, for configuring parameters such as `max_duration`, `max_price`, `termination_idle_duration`,)
[//]: # (`regions`, etc.)
[//]: # ()
[//]: # (Set `default` to `true` in your profile, and it will be applied automatically to any run.)

## Attached mode

By default, `dstack apply` runs in attached mode.
This means it streams the logs as they come in and, in the case of a task, forwards its ports to `localhost`.

To run in detached mode, use `-d` with `dstack apply`.

> If you detached the CLI, you can always re-attach to a run via `dstack logs -a RUN_NAME`.

## GPU

`dstack` natively supports NVIDIA GPU, and Google Cloud TPU accelerator chips.

The `gpu` property withing `resources` (or the `--gpu` option with `dstack apply`)
allows specifying not only memory size but also GPU names, their memory, and quantity.

Examples:

- `1` (any GPU)
- `A100` (A100)
- `24GB..` (any GPU starting from 24GB)
- `24GB..40GB:2` (two GPUs between 24GB and 40GB)
- `A10G,A100` (either A10G or A100)
- `A100:80GB` (one A100 of 80GB)
- `A100:2` (two A100)
- `A100:40GB:2` (two A100 40GB)
- `tpu-v2-8` (`v2` with 8 TPU cores)

??? info "Google Cloud TPU"
    Currently, you can't specify other than 8 TPU cores. This means only single host workloads are supported.
    Support for multiple hosts is coming soon.

## Service quotas

If you're using your own AWS, GCP, Azure, or OCI accounts, before you can use GPUs or spot instances, you have to request the
corresponding service quotas for each type of instance in each region.

??? info "AWS"
    Check this [guide  :material-arrow-top-right-thin:{ .external }](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html){:target="_blank"} on EC2 service quotas.
    The relevant service quotas include:

    - `Running On-Demand P instances` (on-demand V100, A100 80GB x8)
    - `All P4, P3 and P2 Spot Instance Requests` (spot V100, A100 80GB x8)
    - `Running On-Demand G and VT instances` (on-demand T4, A10G, L4)
    - `All G and VT Spot Instance Requests` (spot T4, A10G, L4)
    - `Running Dedicated p5 Hosts` (on-demand H100)
    - `All P5 Spot Instance Requests` (spot H100)

??? info "GCP"
    Check this [guide  :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/compute/resource-usage){:target="_blank"} on Compute Engine service quotas.
    The relevant service quotas include:

    - `NVIDIA V100 GPUs` (on-demand V100)
    - `Preemtible V100 GPUs` (spot V100)
    - `NVIDIA T4 GPUs` (on-demand T4)
    - `Preemtible T4 GPUs` (spot T4)
    - `NVIDIA L4 GPUs` (on-demand L4)
    - `Preemtible L4 GPUs` (spot L4)
    - `NVIDIA A100 GPUs` (on-demand A100)
    - `Preemtible A100 GPUs` (spot A100)
    - `NVIDIA A100 80GB GPUs` (on-demand A100 80GB)
    - `Preemtible A100 80GB GPUs` (spot A100 80GB)
    - `NVIDIA H100 GPUs` (on-demand H100)
    - `Preemtible H100 GPUs` (spot H100)

??? info "Azure"
    Check this [guide  :material-arrow-top-right-thin:{ .external }](https://learn.microsoft.com/en-us/azure/quotas/quickstart-increase-quota-portal){:target="_blank"} on Azure service quotas.
    The relevant service quotas include:

    - `Total Regional Spot vCPUs` (any spot instances)
    - `Standard NCASv3_T4 Family vCPUs` (on-demand T4)
    - `Standard NVADSA10v5 Family vCPUs` (on-demand A10)
    - `Standard NCADS_A100_v4 Family vCPUs` (on-demand A100 80GB)
    - `Standard NDASv4_A100 Family vCPUs` (on-demand A100 40GB x8)
    - `Standard NDAMSv4_A100Family vCPUs` (on-demand A100 80GB x8)
    - `Standard NCadsH100v5 Family vCPUs` (on-demand H100)
    - `Standard NDSH100v5 Family vCPUs` (on-demand H100 x8)

??? info "OCI"
    Check this [guide  :material-arrow-top-right-thin:{ .external }](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/servicelimits.htm#Requesti){:target="_blank"} on requesting OCI service limits increase.
    The relevant service category is compute. The relevant resources include:

    - `GPUs for GPU.A10 based VM and BM instances` (on-demand A10)
    - `GPUs for GPU2 based VM and BM instances` (on-demand P100)
    - `GPUs for GPU3 based VM and BM instances` (on-demand V100)

Note, for AWS, GCP, and Azure, service quota values are measured with the number of CPUs rather than GPUs.
