# Services

A service allows you to deploy a web app or a model as a scalable endpoint. It lets you configure
dependencies, resources, authorizarion, auto-scaling rules, etc.

Services are provisioned behind a [gateway](concepts/gateways.md) which provides an HTTPS endpoint mapped to your domain,
handles authentication, distributes load, and performs auto-scaling.

??? info "Gateways"
    If you're using the open-source server, you must set up a [gateway](concepts/gateways.md) before you can run a service.

    If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
    the gateway is already set up for you.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or
`service.dstack.yml`
are both acceptable).

<div editor-title="service.dstack.yml"> 

```yaml
type: service
# The name is optional, if not specified, generated randomly
name: llama31-service

# If `image` is not specified, dstack uses its default image
python: "3.10"

# Required environment variables
env:
  - HUGGING_FACE_HUB_TOKEN
commands:
  - pip install vllm
  - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct --max-model-len 4096
# Expose the vllm server port
port: 8000

# Use either spot or on-demand instances
spot_policy: auto

resources:
  # Change to what is required
  gpu: 24GB

# Comment if you don't to access the model via https://gateway.<gateway domain>
model:
  type: chat
  name: meta-llama/Meta-Llama-3.1-8B-Instruct
  format: openai
```

</div>

If you don't specify your Docker image, `dstack` uses the [base](https://hub.docker.com/r/dstackai/base/tags) image
(pre-configured with Python, Conda, and essential CUDA drivers).

!!! info "Auto-scaling"
    By default, the service is deployed to a single instance. However, you can specify the
    [number of replicas and scaling policy](reference/dstack.yml/service.md#auto-scaling).
    In this case, `dstack` auto-scales it based on the load.

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/service.md) for all the options supported by
    services, along with multiple examples.

## Run a service

To run a configuration, use the [`dstack apply`](reference/cli/index.md#dstack-apply) command.

<div class="termy">

```shell
$ HUGGING_FACE_HUB_TOKEN=...

$ dstack apply -f service.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE
 1  runpod   CA-MTL-1  18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 2  runpod   EU-SE-1   18xCPU, 100GB, A5000:24GB:2  yes   $0.22
 3  gcp      us-west4  27xCPU, 150GB, A5000:24GB:3  yes   $0.33
 
Submit the run llama31-service? [y/n]: y

Provisioning...
---> 100%

Service is published at https://llama31-service.example.com
```

</div>

`dstack apply` automatically uploads the code from the current repo, including your local uncommitted changes.
To avoid uploading large files, ensure they are listed in `.gitignore`.

## Access the endpoint

One the service is up, its endpoint is accessible at `https://<run name>.<gateway domain>`.

By default, the service endpoint requires the `Authorization` header with `Bearer <dstack token>`.

<div class="termy">

```shell
$ curl https://llama31-service.example.com/v1/chat/completions \
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

Authorization can be disabled by setting [`auth`](reference/dstack.yml/service.md#authorization) to `false` in the
service configuration file.

### Gateway endpoint

In case the service has the [model mapping](reference/dstack.yml/service.md#model-mapping) configured, you will also be
able to access the model at `https://gateway.<gateway domain>` via the OpenAI-compatible interface.

## Manage runs

### List runs

The [`dstack ps`](reference/cli/index.md#dstack-ps)  command lists all running jobs and their statuses. 
Use `--watch` (or `-w`) to monitor the live status of runs.

### Stop a run

Once the run exceeds the [`max_duration`](reference/dstack.yml/task.md#max_duration), or when you use [`dstack stop`](reference/cli/index.md#dstack-stop), 
the dev environment is stopped. Use `--abort` or `-x` to stop the run abruptly. 

[//]: # (TODO: Mention `dstack logs` and `dstack logs -d`)

## Manage fleets

By default, `dstack apply` reuses `idle` instances from one of the existing [fleets](fleets.md), 
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

1. Check the [TGI :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/tgi/README.md){:target="_blank"} and [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/deployment/vllm/README.md){:target="_blank"} examples
2. See [gateways](concepts/gateways.md) on how to set up a gateway
3. Browse [examples](/docs/examples)
4. See [fleets](fleets.md) on how to manage fleets

!!! info "Reference"
    See [.dstack.yml](reference/dstack.yml/service.md) for all the options supported by
    services, along with multiple examples.