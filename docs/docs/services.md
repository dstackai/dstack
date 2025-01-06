# Services

Services allow you to deploy models or any web app as a secure and scalable endpoint.

When running models, services provide access through the unified OpenAI-compatible endpoint.

## Define a configuration

First, define a service configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title="service.dstack.yml"> 

```yaml
type: service
name: llama31

# If `image` is not specified, dstack uses its default image
python: "3.11"
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_MODEL_LEN=4096
commands:
  - pip install vllm
  - vllm serve $MODEL_ID
    --max-model-len $MAX_MODEL_LEN
    --tensor-parallel-size $DSTACK_GPUS_NUM
port: 8000
# Register the model
model: meta-llama/Meta-Llama-3.1-8B-Instruct

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  gpu: 24GB
```

</div>

Note, the `model` property is optional and not needed when deploying a non-OpenAI-compatible model or a regular web app.

!!! info "Docker image"
    If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
    pre-configured with Python, Conda, and essential CUDA drivers.

!!! info "Gateway"
    To enable [auto-scaling](reference/dstack.yml/service.md#auto-scaling), or use a custom domain with HTTPS, 
    set up a [gateway](concepts/gateways.md) before running the service.
    If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
    a gateway is pre-configured for you.

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/service.md) for all the options supported by
    services, along with multiple examples.

## Run a service

To run a service, pass the configuration to [`dstack apply`](reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f service.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:3  yes   $0.33
 
Submit the run llama31? [y/n]: y

Provisioning...
---> 100%

Service is published at: 
  http://localhost:3000/proxy/services/main/llama31/
Model meta-llama/Meta-Llama-3.1-8B-Instruct is published at:
  http://localhost:3000/proxy/models/main/
```

</div>

`dstack apply` automatically provisions instances, uploads the contents of the repo (incl. your local uncommitted changes),
and runs the service.

## Access the endpoint

### Service

If a [gateway](concepts/gateways.md) is not configured, the service’s endpoint will be accessible at
`<dstack server URL>/proxy/services/<project name>/<run name>/`.
If a [gateway](concepts/gateways.md) is configured, the service endpoint will be accessible at
`https://<run name>.<gateway domain>`.

<div class="termy">

```shell
$ curl http://localhost:3000/proxy/services/main/llama31/v1/chat/completions \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -d '{
        "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
        "messages": [
            {
                "role": "user",
                "content": "Compose a poem that explains the concept of recursion in programming."
            }
        ]
    }'
```

</div>

!!! info "Auth"
    By default, the service endpoint requires the `Authorization` header with `Bearer <dstack token>`.
    Authorization can be disabled by setting [`auth`](reference/dstack.yml/service.md#authorization) to `false` in the
    service configuration file.

### Model

If the service defines the `model` property, the model can be accessed with
the OpenAI-compatible endpoint at `<dstack server URL>/proxy/models/<project name>/`,
or via the control plane UI's playground.

When a [gateway](concepts/gateways.md) is configured, the OpenAI-compatible endpoint is available at `https://gateway.<gateway domain>/`.

## Manage runs

### List runs

The [`dstack ps`](reference/cli/dstack/ps.md)  command lists all running jobs and their statuses. 
Use `--watch` (or `-w`) to monitor the live status of runs.

### Stop a run

A service runs until you stop it or its lifetime exceeds [`max_duration`](reference/dstack.yml/dev-environment.md#max_duration).
To gracefully stop a service, use [`dstack stop`](reference/cli/dstack/stop.md).
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
If no `idle` instances match the requirements, it automatically creates a new fleet 
using backends.

To ensure `dstack apply` doesn't create a new fleet but reuses an existing one,
pass `-R` (or `--reuse`) to `dstack apply`.

<div class="termy">

```shell
$ dstack apply -R -f examples/.dstack.yml
```

</div>

Alternatively, set [`creation_policy`](reference/dstack.yml/dev-environment.md#creation_policy) to `reuse` in the run configuration.

### Idle duration

If a fleet is created automatically, it stays `idle` for 5 minutes by default and can be reused within that time.
If the fleet is not reused within this period, it is automatically terminated.
To change the default idle duration, set
[`idle_duration`](reference/dstack.yml/fleet.md#idle_duration) in the run configuration (e.g., `0s`, `1m`, or `off` for
unlimited).

!!! info "Fleets"
    For greater control over fleet provisioning, configuration, and lifecycle management, it is recommended to use
    [fleets](concepts/fleets.md) directly.

## What's next?

1. Read about [dev environments](dev-environments.md), [tasks](tasks.md), and [repos](concepts/repos.md)
2. Learn how to manage [fleets](concepts/fleets.md)
3. See how to set up [gateways](concepts/gateways.md)
4. Check the [TGI :material-arrow-top-right-thin:{ .external }](/examples/deployment/tgi/){:target="_blank"},
   [vLLM :material-arrow-top-right-thin:{ .external }](/examples/deployment/vllm/){:target="_blank"}, and 
   [NIM :material-arrow-top-right-thin:{ .external }](/examples/deployment/nim/){:target="_blank"} examples

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/service.md) for all the options supported by
    services, along with multiple examples.
