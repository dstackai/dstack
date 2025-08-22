# Protips

Below are tips and tricks to use `dstack` more efficiently.

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

## Tasks

Tasks can be used not only for batch jobs but also for web applications.

<div editor-title="app.dstack.yml">

```yaml
type: task
name: streamlit-task

python: 3.12

commands:
  - uv pip install streamlit
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

!!! info "Tasks vs. services"
    [Services](../concepts/services.md) provide external access, `https`, replicas with autoscaling, OpenAI-compatible endpoint
    and other service features. If you don't need them, you can use [tasks](../concepts/tasks.md) for running apps.

## Utilization policy

If you want your run to automatically terminate if any of GPUs are underutilized, you can specify `utilization_policy`.

Below is an example of a dev environment that auto-terminate if any GPU stays below 10% utilization for 1 hour.

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: my-dev

python: 3.12
ide: cursor

resources:
  gpu: H100:8

utilization_policy:
  min_gpu_utilization: 10
  time_window: 1h
```

</div>

## Docker in Docker

Set `docker` to `true` to enable the `docker` CLI in your dev environment, e.g., to run or build Docker images, or use Docker Compose.

=== "Dev environment"
    <div editor-title="examples/misc/docker-compose/.dstack.yml">

    ```yaml
    type: dev-environment
    name: vscode

    docker: true

    ide: vscode
    init:
      - docker run --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi
    ```

    </div>

=== "Task"
    <div editor-title="examples/misc/dind/task.dstack.yml">

    ```yaml
    type: task
    name: docker-nvidia-smi

    docker: true

    commands:
      - docker run --gpus all nvidia/cuda:12.3.0-base-ubuntu22.04 nvidia-smi

    resources:
      gpu: 1
    ```

    </div>

??? info "Volumes"

    To persist Docker data between runs (e.g. images, containers, volumes, etc), create a `dstack` [volume](../concepts/volumes.md)
    and add attach it in your run configuration.

    === "Network volums"
    
        ```yaml
            type: dev-environment
            name: vscode
        
            docker: true
            ide: vscode
        
            volumes:
              - name: docker-volume
                path: /var/lib/docker
        ```

    === "Instance volumes"

        ```yaml
            type: dev-environment
            name: vscode
        
            docker: true
            ide: vscode
        
            volumes:
              - name: /docker-volume
                path: /var/lib/docker
                optional: true
        ```

See more Docker examples [here](https://github.com/dstackai/dstack/tree/master/examples/misc/docker-compose).

## Fleets

### Creation policy

By default, when you run `dstack apply` with a dev environment, task, or service,
`dstack` reuses `idle` instances from an existing [fleet](../concepts/fleets.md).
If no `idle` instances match the requirements, `dstack` automatically creates a new fleet 
using configured backends.

To ensure `dstack apply` doesn't create a new fleet but reuses an existing one,
pass `-R` (or `--reuse`) to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -R -f examples/.dstack.yml
```

</div>

### Idle duration

If a fleet is created automatically, it stays `idle` for 5 minutes by default and can be reused within that time.
If the fleet is not reused within this period, it is automatically terminated.
To change the default idle duration, set
[`idle_duration`](../reference/dstack.yml/fleet.md#idle_duration) in the run configuration (e.g., `0s`, `1m`, or `off` for
unlimited).

> For greater control over fleet provisioning, configuration, and lifecycle management, it is recommended to use
> [fleets](../concepts/fleets.md) directly.

## Volumes

To persist data across runs, it is recommended to use volumes.
`dstack` supports two types of volumes: [network](../concepts/volumes.md#network) 
(for persisting data even if the instance is interrupted)
and [instance](../concepts/volumes.md#instance) (useful for persisting cached data across runs while the instance remains active).

> If you use [SSH fleets](../concepts/fleets.md#ssh), you can mount network storage (e.g., NFS or SMB) to the hosts and access it in runs via instance volumes.

## Environment variables

If a configuration requires an environment variable that you don't want to hardcode in the YAML, you can define it
without assigning a value:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment
name: vscode

python: 3.12

env:
  - HF_TOKEN
ide: vscode
```

</div>

Then, you can pass the environment variable either via the shell:

<div class="termy">

```shell
$ HF_TOKEN=... 
$ dstack apply -f .dstack.yml
```

</div>

Or via the `-e` option of the `dstack apply` command:

<div class="termy">

```shell
$ dstack apply -e HF_TOKEN=... -f .dstack.yml
```

</div>

??? info ".envrc"
    A better way to configure environment variables not hardcoded in YAML is by specifying them in a `.envrc` file:

    <div editor-title=".envrc"> 

    ```shell
    export HF_TOKEN=...
    ```

    </div>
    
    If you install [`direnv` :material-arrow-top-right-thin:{ .external }](https://direnv.net/){:target="_blank"},
    it will automatically apply the environment variables from the `.envrc` file to the `dstack apply` command.

    Remember to add `.envrc` to `.gitignore` to avoid committing it to the repo.    

[//]: # (## Profiles)
[//]: # ()
[//]: # (If you don't want to specify the same parameters for each configuration, you can define them once via [profiles]&#40;../reference/profiles.yml.md&#41;)
[//]: # (and reuse them across configurations.)
[//]: # ()
[//]: # (This can be handy, for example, for configuring parameters such as `max_duration`, `max_price`, `termination_idle_time`,)
[//]: # (`regions`, etc.)
[//]: # ()
[//]: # (Set `default` to `true` in your profile, and it will be applied automatically to any run.)

## Retry policy

By default, if `dstack` can't find available capacity, the run will fail.

If you'd like `dstack` to automatically retry, configure the 
[retry](../reference/dstack.yml/task.md#retry) property accordingly:

<!-- TODO: Add a relevant example here -->

<div editor-title=".dstack.yml">

```yaml
type: task
name: train    

python: 3.12

commands:
  - uv pip install -r fine-tuning/qlora/requirements.txt
  - python fine-tuning/qlora/train.py

retry:
  on_events: [no-capacity]
  # Retry for up to 1 hour
  duration: 1h
```

</div>

## Projects

If you're using multiple `dstack` projects (e.g., from different `dstack` servers),  
you can switch between them using the [`dstack project`](../reference/cli/dstack/project.md) command.

??? info ".envrc"
    Alternatively, you can install [`direnv` :material-arrow-top-right-thin:{ .external }](https://direnv.net/){:target="_blank"}  
    to automatically apply environment variables from the `.envrc` file in your project directory.

    <div editor-title=".envrc"> 

    ```shell
    export DSTACK_PROJECT=main
    ```

    </div>

    Now, `dstack` will always use this project within this directory.

    Remember to add `.envrc` to `.gitignore` to avoid committing it to the repo. 

## Attached mode

By default, `dstack apply` runs in attached mode.
This means it streams the logs as they come in and, in the case of a task, forwards its ports to `localhost`.

To run in detached mode, use `-d` with `dstack apply`.

> If you detached the CLI, you can always re-attach to a run via [`dstack attach`](../reference/cli/dstack/attach.md).

## GPU specification

`dstack` natively supports NVIDIA GPU, AMD GPU, and Google Cloud TPU accelerator chips.

The `gpu` property within [`resources`](../reference/dstack.yml/dev-environment.md#resources) (or the `--gpu` option with [`dstack apply`](../reference/cli/dstack/apply.md) or
[`dstack offer`](../reference/cli/dstack/offer.md))
allows specifying not only memory size but also GPU vendor, names, their memory, and quantity.

The general format is: `<vendor>:<comma-sparated names>:<memory range>:<quantity range>`.

Each component is optional. 

<!-- TODO: Mention, if count is not specified, it's set to `1..` -->

Ranges can be:

* **Closed** (e.g. `24GB..80GB` or `1..8`)
* **Open** (e.g. `24GB..` or `1..`)
* **Single values** (e.g. `1` or `24GB`).

Examples:

- `1` (any GPU)
- `amd:2` (two AMD GPUs)
- `A100` (A100)
- `24GB..` (any GPU starting from 24GB)
- `24GB..40GB:2` (two GPUs between 24GB and 40GB)
- `A10G,A100` (either A10G or A100)
- `A100:80GB` (one A100 of 80GB)
- `A100:2` (two A100)
- `MI300X:4` (four MI300X)
- `A100:40GB:2` (two A100 40GB)
- `tpu:v2-8` (`v2` Google Cloud TPU with 8 cores)

The GPU vendor is indicated by one of the following case-insensitive values:

- `nvidia` (NVIDIA GPUs)
- `amd` (AMD GPUs)
- `tpu` (Google Cloud TPUs)

??? info "AMD"
    Currently, when an AMD GPU is specified, either by name or by vendor, the `image` property must be specified as well.

??? info "TPU"
    Currently, you can't specify other than 8 TPU cores. This means only single host workloads are supported.
    Support for multiple hosts is coming soon.

## Offers

If you're not sure which offers (hardware configurations) are available with the configured backends, use the
[`dstack offer`](../reference/cli/dstack/offer.md#list-gpu-offers) command.

<div class="termy">

```shell
$ dstack offer --gpu H100 --max-offers 10
Getting offers...
---> 100%

 #   BACKEND     REGION     INSTANCE TYPE          RESOURCES                                     SPOT  PRICE   
 1   datacrunch  FIN-01     1H100.80S.30V          30xCPU, 120GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 2   datacrunch  FIN-02     1H100.80S.30V          30xCPU, 120GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 3   datacrunch  FIN-02     1H100.80S.32V          32xCPU, 185GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 4   datacrunch  ICE-01     1H100.80S.32V          32xCPU, 185GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.19   
 5   runpod      US-KS-2    NVIDIA H100 PCIe       16xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.39   
 6   runpod      CA         NVIDIA H100 80GB HBM3  24xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.69   
 7   nebius      eu-north1  gpu-h100-sxm           16xCPU, 200GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.95   
 8   runpod      AP-JP-1    NVIDIA H100 80GB HBM3  20xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.99   
 9   runpod      CA-MTL-1   NVIDIA H100 80GB HBM3  28xCPU, 251GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.99   
 10  runpod      CA-MTL-2   NVIDIA H100 80GB HBM3  26xCPU, 125GB, 1xH100 (80GB), 100.0GB (disk)  no    $2.99   
     ...                                                                                                                
 Shown 10 of 99 offers, $127.816 max
```

</div>

??? info "Grouping offers"
    Use `--group-by` to aggregate offers. Accepted values: `gpu`, `backend`, `region`, and `count`.

    <div class="termy">

    ```shell
    dstack offer --gpu b200 --group-by gpu,backend,region
    Project      main
    User         admin
    Resources    cpu=2.. mem=8GB.. disk=100GB.. b200:1..
    Spot policy  auto
    Max price    -
    Reservation  -
    Group by     gpu, backend, region

    #   GPU              SPOT             $/GPU       BACKEND  REGION
    1   B200:180GB:1..8  spot, on-demand  3.59..5.99  runpod   EU-RO-1
    2   B200:180GB:1..8  spot, on-demand  3.59..5.99  runpod   US-CA-2
    3   B200:180GB:8     on-demand        4.99        lambda   us-east-1
    4   B200:180GB:8     on-demand        5.5         nebius   us-central1
    ```

    </div>

    When using `--group-by`, `gpu` must always be `included`.
    The `region` value can only be used together with `backend`.

The `offer` command allows you to filter and group offers with various [advanced options](../reference/cli/dstack/offer.md#usage).


## Metrics

`dstack` tracks essential metrics accessible via the CLI and UI. To access advanced metrics like DCGM, configure the server to export metrics to Prometheus. See [Metrics](metrics.md) for details.

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

[//]: # (TODO: Mention spot policy)
