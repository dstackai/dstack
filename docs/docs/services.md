# Services

A service allows you to deploy a model or a web app as an endpoint. It lets you configure
dependencies, resources, authorization, auto-scaling rules, etc.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or
`service.dstack.yml`
are both acceptable).

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

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

Note, the `model` property is optional and not needed when deploying a non-OpenAI-compatible model or a regular web app.

!!! info "Gateway"
    To enable [auto-scaling](reference/dstack.yml/service.md#auto-scaling), or use a custom domain with HTTPS, 
    set up a [gateway](concepts/gateways.md) before running the service.
    If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
    a gateway is pre-configured for you.

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/service.md) for all the options supported by
    services, along with multiple examples.

## Run a service

To run a configuration, use the [`dstack apply`](reference/cli/index.md#dstack-apply) command.

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
  http://localhost:3000/proxy/models/main/ (OpenAI-compatible)
```

</div>

`dstack apply` automatically uploads the code from the current repo, including your local uncommitted changes.
To avoid uploading large files, ensure they are listed in `.gitignore`.

## Access the endpoint

### Service

If no gateway is created, the service’s endpoint will be accessible at
`<dstack server URL>/proxy/services/<project name>/<run name>/`.

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

When a [gateway](concepts/gateways.md) is configured, the service endpoint will be accessible at `https://<run name>.<gateway domain>`.

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

1. Check the [TGI :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi/README.md){:target="_blank"},
   [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/README.md){:target="_blank"}, and 
   [NIM :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/nim/README.md){:target="_blank"} examples
2. See [gateways](concepts/gateways.md) on how to set up a gateway
3. Browse [examples](/examples)
4. See [fleets](concepts/fleets.md) on how to manage fleets

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/service.md) for all the options supported by
    services, along with multiple examples.
