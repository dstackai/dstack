# Protips

Below are tips and tricks to use `dstack` more efficiently.

### Dev environments

Before running a task or service, it's recommended that you first start with a dev environment. Dev environments
allow you to run commands interactively.

Once the commands work, go ahead and run them as a task or a service.

??? tip "Jupyter"
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

### Tasks

Tasks can be used not only for batch jobs but also for web applications.

<div editor-title="app.dstack.yml">

```yaml
type: task

python: "3.11"

commands:
  - pip3 install streamlit
  - streamlit hello

ports: 
  - 8501

```

</div>

While you run a task, `dstack` forwards the remote ports to `localhost`.

<div class="termy">

```shell
$ dstack run . -f app.dstack.yml

  Welcome to Streamlit. Check out our demo in your browser.

  Local URL: http://localhost:8501
```

</div>

This allows you to access the remote `8501` port on `localhost:8501` while you the CLI is attached.

??? info "Port mapping"
    If you want to override the local port, use the `--port` option:
        
    <div class="termy">
    
    ```shell
    $ dstack run . -f app.dstack.yml --port 3000:8501
    ```
    
    </div>
    
    This will forward the remote `8501` port to `localhost:3000`.

If the task works, go ahead and run it as a service.

### Environment variables

If a configuration requires an environment variable that you don't want to hardcode in the YAML, you can define it
without assigning a value:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment

env:
  - HUGGING_FACE_HUB_TOKEN

python: "3.11"
ide: vscode
```

</div>

Then, you can pass the environment variable either via the shell:

```shell
HUGGING_FACE_HUB_TOKEN=... dstack run . -f .dstack.yml
```

Or via the `-e` option of the `dstack run` command:

```shell
dstack run . -f .dstack.yml -e HUGGING_FACE_HUB_TOKEN=...
```

!!! tip ".env"
    A better way to configure environment variables not hardcoded in YAML is by specifying them in a `.env` file:

    ```
    HUGGING_FACE_HUB_TOKEN=...
    ```
    
    If you install [`direnv` :material-arrow-top-right-thin:{ .external }](https://direnv.net/){:target="_blank"},
    it will automatically pass the environment variables from the `.env` file to the `dstack run` command.

    Remember to add `.env` to `.gitignore` to avoid pushing it to the repo.    

### Idle instances

By default, the `dstack` run command reuses an idle instance from the pool. If no instance matches the requirements, it creates a new one.

When the run finishes, the instance remains idle for the configured time (by default, `5m`) before it gets destroyed.

You can change the default idle duration by using ``--idle-duration DURATION`` with `dstack run`, or
set `termination_idle_duration` in the configuration or profile.

An idle instance can be destroyed at any time via `dstack pool remove INSTANCE_NAME`.

### Profiles

If you don't want to specify the same parameters for each configuration, you can define them once via [profiles](reference/profiles.yml.md)
and reuse them across configurations.

This can be handy, for example, for configuring parameters such as `max_duration`, `max_price`, `termination_idle_duration`,
`regions`, etc.

Set `d`efault to true in your profile, and it will be applied automatically to any run.

## Attached mode

By default, `dstack run` runs in attached mode.
This means it streams the logs as they come in and, in the case of a task, forwards its ports to `localhost`.

If you detach the CLI, you can re-attach it using `dstack logs -a RUN_NAME`.

To run in detached mode, use `-d` with `dstack run`.

## GPU

The `gpu` property withing `resources` (or the `--gpu` option with `dstack run`)
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

## Service quotas

If you're using your own AWS, GCP, or Azure accounts, before you can use GPUs or spot instances, you have to request the
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
    Check this [guide  :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/compute/resource-usage){:target="_blank"} on Compute Engine service quotas.
    The relevant service quotas include:

    - `Total Regional Spot vCPUs` (any spot instances)
    - `Standard NCASv3_T4 Family vCPUs` (on-demand T4)
    - `Standard NVADSA10v5 Family vCPUs` (on-demand A10)
    - `Standard NCADS_A100_v4 Family vCPUs` (on-demand A100 80GB)
    - `Standard NDASv4_A100 Family vCPUs` (on-demand A100 40GB x8)
    - `Standard NDAMSv4_A100Family vCPUs` (on-demand A100 80GB x8)
    - `Standard NCadsH100v5 Family vCPUs` (on-demand H100)
    - `Standard NDSH100v5 Family vCPUs` (on-demand H100 x8)

Note, for AWS, GCP, and Azure, service quota values are measured with the number of CPUs rather than GPUs.

## Data and models

For loading and saving data, it's best to use object storage like S3 or HuggingFace Datasets.

For models, it's best to use services like HuggingFace Hub.