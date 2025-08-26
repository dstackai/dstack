# Services

Services allow you to deploy models or web apps as secure and scalable endpoints.

## Apply a configuration

First, define a service configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `dev.dstack.yml` are both acceptable).

<div editor-title=".dstack.yml"> 

```yaml
type: service
name: llama31

# If `image` is not specified, dstack uses its default image
python: 3.12
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_MODEL_LEN=4096
commands:
  - uv pip install vllm
  - vllm serve $MODEL_ID
    --max-model-len $MAX_MODEL_LEN
    --tensor-parallel-size $DSTACK_GPUS_NUM
port: 8000
# (Optional) Register the model
model: meta-llama/Meta-Llama-3.1-8B-Instruct

# Uncomment to leverage spot instances
#spot_policy: auto

resources:
  gpu: 24GB
```

</div>

To run a service, pass the configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ HF_TOKEN=...
$ dstack apply -f .dstack.yml

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

`dstack apply` automatically provisions instances and runs the service.

If a [gateway](gateways.md) is not configured, the service’s endpoint will be accessible at
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

If the service defines the [`model`](#model) property, the model can be accessed with
the global OpenAI-compatible endpoint at `<dstack server URL>/proxy/models/<project name>/`,
or via `dstack` UI.

If [authorization](#authorization) is not disabled, the service endpoint requires the `Authorization` header with
`Bearer <dstack token>`.

??? info "Gateway"
    Running services for development purposes doesn’t require setting up a [gateway](gateways.md).

    However, you'll need a gateway in the following cases:

    * To use auto-scaling or rate limits
    * To enable HTTPS for the endpoint and map it to your domain
    * If your service requires WebSockets
    * If your service cannot work with a [path prefix](#path-prefix)

    Note, if you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
    a gateway is already pre-configured for you.

    If a [gateway](gateways.md) is configured, the service endpoint will be accessible at
    `https://<run name>.<gateway domain>/`.

    If the service defines the `model` property, the model will be available via the global OpenAI-compatible endpoint 
    at `https://gateway.<gateway domain>/`.

## Configuration options

### Replicas and scaling

By default, `dstack` runs a single replica of the service.
You can configure the number of replicas as well as the auto-scaling rules.

<div editor-title="service.dstack.yml"> 

```yaml
type: service
name: llama31-service

python: 3.12

env:
  - HF_TOKEN
commands:
  - uv pip install vllm
  - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct --max-model-len 4096
port: 8000

resources:
  gpu: 24GB

replicas: 1..4
scaling:
  # Requests per seconds
  metric: rps
  # Target metric value
  target: 10
```

</div>

The [`replicas`](../reference/dstack.yml/service.md#replicas) property can be a number or a range.

The [`metric`](../reference/dstack.yml/service.md#metric) property of [`scaling`](../reference/dstack.yml/service.md#scaling) only supports the `rps` metric (requests per second). In this 
case `dstack` adjusts the number of replicas (scales up or down) automatically based on the load. 

Setting the minimum number of replicas to `0` allows the service to scale down to zero when there are no requests.

> The `scaling` property requires creating a [gateway](gateways.md).

### Model

If the service is running a chat model with an OpenAI-compatible interface,
set the [`model`](#model) property to make the model accessible via `dstack`'s 
global OpenAI-compatible endpoint, and also accessible via `dstack`'s UI.

### Authorization

By default, the service enables authorization, meaning the service endpoint requires a `dstack` user token.
This can be disabled by setting `auth` to `false`.

<div editor-title="examples/misc/http.server/service.dstack.yml"> 

```yaml
type: service
name: http-server-service

# Disable authorization
auth: false

python: 3.12

commands:
  - python3 -m http.server
port: 8000
```

</div>

### Probes

Configure one or more HTTP probes to periodically check the health of the service.

<div editor-title="service.dstack.yml">

```yaml
type: service
name: my-service
port: 80
image: my-app:latest
probes:
- type: http
  url: /health
  interval: 15s
```

</div>

You can track probe statuses in `dstack ps --verbose`.

<div class="termy">

```shell
$ dstack ps --verbose

 NAME                            BACKEND          STATUS   PROBES  SUBMITTED
 my-service deployment=1                          running          11 mins ago
   replica=0 job=0 deployment=0  aws (us-west-2)  running  ✓       11 mins ago
   replica=1 job=0 deployment=1  aws (us-west-2)  running  ×       1 min ago
```

</div>

??? info "Probe statuses"
    The following symbols are used for probe statuses:

    - `×` &mdash; the last probe execution failed.
    - `~` &mdash; the last probe execution succeeded, but the [`ready_after`](../reference/dstack.yml/service.md#ready_after) threshold is not yet reached.
    - `✓` &mdash; the last `ready_after` probe executions succeeded.

    If multiple probes are configured for the service, their statuses are displayed in the order in which the probes appear in the configuration.

Probes are executed for each service replica while the replica is `running`. A probe execution is considered successful if the replica responds with a `2xx` status code. Probe statuses do not affect how `dstack` handles replicas, except during [rolling deployments](#rolling-deployment).

??? info "HTTP request configuration"
    You can configure the HTTP request method, headers, and other properties. To include secret values in probe requests, use environment variable interpolation, which is enabled for the `url`, `headers[i].value`, and `body` properties.

    <div editor-title="service.dstack.yml">

    ```yaml
    type: service
    name: my-service
    port: 80
    image: my-app:latest
    env:
    - PROBES_API_KEY
    probes:
    - type: http
      method: post
      url: /check-health
      headers:
      - name: X-API-Key
        value: ${{ env.PROBES_API_KEY }}
      - name: Content-Type
        value: application/json
      body: '{"level": 2}'
      timeout: 20s
    ```

    </div>

See the [reference](../reference/dstack.yml/service.md#probes) for more probe configuration options.

### Path prefix { #path-prefix }

If your `dstack` project doesn't have a [gateway](gateways.md), services are hosted with the
`/proxy/services/<project name>/<run name>/` path prefix in the URL.
When running web apps, you may need to set some app-specific settings
so that browser-side scripts and CSS work correctly with the path prefix.

<div editor-title="dash.dstack.yml"> 

```yaml
type: service
name: dash
gateway: false

auth: false
# Do not strip the path prefix
strip_prefix: false

env:
  # Configure Dash to work with a path prefix
  # Replace `main` with your dstack project name
  - DASH_ROUTES_PATHNAME_PREFIX=/proxy/services/main/dash/

commands:
  - uv pip install dash
  # Assuming the Dash app is in your repo at app.py
  - python app.py

port: 8050
```

</div>

By default, `dstack` strips the prefix before forwarding requests to your service,
so to the service it appears as if the prefix isn't there. This allows some apps
to work out of the box. If your app doesn't expect the prefix to be stripped,
set [`strip_prefix`](../reference/dstack.yml/service.md#strip_prefix) to `false`.

If your app cannot be configured to work with a path prefix, you can host it
on a dedicated domain name by setting up a [gateway](gateways.md).

### Rate limits { #rate-limits }

If you have a [gateway](gateways.md), you can configure rate limits for your service
using the [`rate_limits`](../reference/dstack.yml/service.md#rate_limits) property.

<div editor-title="service.dstack.yml"> 

```yaml
type: service
image: my-app:latest
port: 80

rate_limits:
# For /api/auth/* - 1 request per second, no bursts
- prefix: /api/auth/
  rps: 1
# For other URLs - 4 requests per second + bursts of up to 9 requests
- rps: 4
  burst: 9
```

</div>

The rps limit sets the max requests per second, tracked in milliseconds (e.g., `rps: 4` means 1 request every 250 ms). Use `burst` to allow short spikes while keeping the average within `rps`.

Limits apply to the whole service (all replicas) and per client (by IP). Clients exceeding the limit get a 429 error.

??? info "Partitioning key"
    Instead of partitioning requests by client IP address,
    you can choose to partition by the value of a header.

    <div editor-title="service.dstack.yml"> 

    ```yaml
    type: service
    image: my-app:latest
    port: 80

    rate_limits:
    - rps: 4
      burst: 9
      # Apply to each user, as determined by the `Authorization` header
      key:
        type: header
        header: Authorization
    ```

    </div>

### Resources

If you specify memory size, you can either specify an explicit size (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: service
name: llama31-service

python: 3.12
env:
  - HF_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_MODEL_LEN=4096
commands:
  - uv pip install vllm
  - |
    vllm serve $MODEL_ID
      --max-model-len $MAX_MODEL_LEN
      --tensor-parallel-size $DSTACK_GPUS_NUM
port: 8000

resources:
  # 16 or more x86_64 cores
  cpu: 16..
  # 2 GPUs of 80GB
  gpu: 80GB:2

  # Minimum disk size
  disk: 200GB
```

</div>

The `cpu` property lets you set the architecture (`x86` or `arm`) and core count — e.g., `x86:16` (16 x86 cores), `arm:8..` (at least 8 ARM cores). 
If not set, `dstack` infers it from the GPU or defaults to `x86`.

The `gpu` property lets you specify vendor, model, memory, and count — e.g., `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either), `A100:80GB` (one 80GB A100), `A100:2` (two A100), `24GB..40GB:2` (two GPUs with 24–40GB), `A100:40GB:2` (two 40GB A100s). 

If vendor is omitted, `dstack` infers it from the model or defaults to `nvidia`.

<!-- ??? info "Google Cloud TPU"
    To use TPUs, specify its architecture via the `gpu` property.

    ```yaml
    type: service
    name: llama31-service-optimum-tpu
    
    image: dstackai/optimum-tpu:llama31
    env:
      - HF_TOKEN
      - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
      - MAX_TOTAL_TOKENS=4096
      - MAX_BATCH_PREFILL_TOKENS=4095
    commands:
      - text-generation-launcher --port 8000
    port: 8000
    # Register the model
    model: meta-llama/Meta-Llama-3.1-8B-Instruct
    
    resources:
      gpu: v5litepod-4
    ```

    Currently, only 8 TPU cores can be specified, supporting single TPU device workloads. Multi-TPU support is coming soon. -->

??? info "Shared memory"
    If you are using parallel communicating processes (e.g., dataloaders in PyTorch), you may need to configure 
    `shm_size`, e.g. set it to `16GB`.

> If you’re unsure which offers (hardware configurations) are available from the configured backends, use the
> [`dstack offer`](../reference/cli/dstack/offer.md#list-gpu-offers) command to list them.


### Docker

#### Default image

If you don't specify `image`, `dstack` uses its base Docker image pre-configured with 
`uv`, `python`, `pip`, essential CUDA drivers, and NCCL tests (under `/opt/nccl-tests/build`). 

Set the `python` property to pre-install a specific version of Python.

<!-- TODO: Add a relevant example -->

<div editor-title=".dstack.yml"> 

```yaml
type: service
name: http-server-service    

python: 3.12

commands:
  - python3 -m http.server
port: 8000
```

</div>

#### NVCC

By default, the base Docker image doesn’t include `nvcc`, which is required for building custom CUDA kernels. 
If you need `nvcc`, set the [`nvcc`](../reference/dstack.yml/dev-environment.md#nvcc) property to true.

<!-- TODO: Add a relevant example -->

<div editor-title="service.dstack.yml"> 

```yaml
type: service
name: http-server-service    

python: 3.12
nvcc: true

commands:
  - python3 -m http.server
port: 8000
```

</div>

#### Custom image

If you want, you can specify your own Docker image via `image`.

<div editor-title=".dstack.yml">

    ```yaml
    type: service
    name: http-server-service

    image: python
    
    commands:
      - python3 -m http.server
    port: 8000
    ```

</div>

#### Docker in Docker

Set `docker` to `true` to enable the `docker` CLI in your service, e.g., to run Docker images or use Docker Compose.

<div editor-title="examples/misc/docker-compose/service.dstack.yml"> 

```yaml
type: service
name: chat-ui-task

auth: false

docker: true

working_dir: examples/misc/docker-compose
commands:
  - docker compose up
port: 9000
```

</div>

Cannot be used with `python` or `image`. Not supported on `runpod`, `vastai`, or `kubernetes`.

#### Privileged mode

To enable privileged mode, set [`privileged`](../reference/dstack.yml/dev-environment.md#privileged) to `true`.

Not supported with `runpod`, `vastai`, and `kubernetes`.

#### Private registry
    
Use the [`registry_auth`](../reference/dstack.yml/dev-environment.md#registry_auth) property to provide credentials for a private Docker registry. 

```yaml
type: service
name: serve-distill-deepseek

env:
  - NGC_API_KEY
  - NIM_MAX_MODEL_LEN=4096

image: nvcr.io/nim/deepseek-ai/deepseek-r1-distill-llama-8b
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}
port: 8000

model: deepseek-ai/deepseek-r1-distill-llama-8b

resources:
  gpu: H100:1
```
    
### Environment variables

<div editor-title=".dstack.yml">

```yaml
type: service
name: llama-2-7b-service

python: 3.12

env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - uv pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB
```

</div>

> If you don't assign a value to an environment variable (see `HF_TOKEN` above),
`dstack` will require the value to be passed via the CLI or set in the current process.

??? info "System environment variables"
    The following environment variables are available in any run by default:
    
    | Name                    | Description                             |
    |-------------------------|-----------------------------------------|
    | `DSTACK_RUN_NAME`       | The name of the run                     |
    | `DSTACK_REPO_ID`        | The ID of the repo                      |
    | `DSTACK_GPUS_NUM`       | The total number of GPUs in the run     |

<!-- TODO: Ellaborate on using environment variables in `registry_auth` -->

### Files

Sometimes, when you run a service, you may want to mount local files. This is possible via the [`files`](../reference/dstack.yml/task.md#_files) property. Each entry maps a local directory or file to a path inside the container.

<!-- TODO: Add a more relevant example -->

<div editor-title="examples/.dstack.yml"> 

```yaml
type: service
name: llama-2-7b-service

files:
  - .:examples  # Maps the directory where `.dstack.yml` to `/workflow/examples`
  - ~/.ssh/id_rsa:/root/.ssh/id_rsa  # Maps `~/.ssh/id_rsa` to `/root/.ssh/id_rsa`

python: 3.12

env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - uv pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB
```

</div>

Each entry maps a local directory or file to a path inside the container. Both local and container paths can be relative or absolute.

If the local path is relative, it’s resolved relative to the configuration file. If the container path is relative, it’s resolved relative to `/workflow`.

The container path is optional. If not specified, it will be automatically calculated.

<!-- TODO: Add a more relevant example -->

<div editor-title="examples/.dstack.yml"> 

```yaml
type: service
name: llama-2-7b-service

files:
  - ../examples  # Maps `examples` (the parent directory of `.dstack.yml`) to `/workflow/examples`
  - ~/.ssh/id_rsa  # Maps `~/.ssh/id_rsa` to `/root/.ssh/id_rsa`

python: 3.12

env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - uv pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB
```

</div>

??? info "Upload limit and excludes"
    Whether its a file or folder, each entry is limited to 2MB. To avoid exceeding this limit, make sure to exclude unnecessary files
    by listing it via `.gitignore` or `.dstackignore`.
    The 2MB upload limit can be increased by setting the `DSTACK_SERVER_CODE_UPLOAD_LIMIT` environment variable.

### Repos

Sometimes, you may want to mount an entire Git repo inside the container.

Imagine you have a cloned Git repo containing an `examples` subdirectory with a `.dstack.yml` file:

<!-- TODO: Add a more relevant example -->

<div editor-title="examples/.dstack.yml"> 

```yaml
type: service
name: llama-2-7b-service

repos:
  # Mounts the parent directory of `examples` (must be a Git repo)
  #   to `/workflow` (the default working directory)
  - ..

python: 3.12

env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - uv pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB
```

</div>

When you run it, `dstack` fetches the repo on the instance, applies your local changes, and mounts it—so the container matches your local repo.

The local path can be either relative to the configuration file or absolute.

??? info "Path"
    Currently, `dstack` always mounts the repo to `/workflow` inside the container. It's the default working directory. 
    Starting with the next release, it will be possible to specify a custom container path.

??? info "Local diff limit and excludes"
    The local diff size is limited to 2MB. To avoid exceeding this limit, exclude unnecessary files
    via `.gitignore` or `.dstackignore`.
    The 2MB local diff limit can be increased by setting the `DSTACK_SERVER_CODE_UPLOAD_LIMIT` environment variable.

??? info "Repo URL"

    Sometimes you may want to mount a Git repo without cloning it locally. In this case, simply provide a URL in `repos`:

    <!-- TODO: Add a more relevant example -->

    <div editor-title="examples/.dstack.yml"> 

    ```yaml
    type: service
    name: llama-2-7b-service

    repos:
      # Clone the specified repo to `/workflow` (the default working directory)
      - https://github.com/dstackai/dstack

    python: 3.12

    env:
      - HF_TOKEN
      - MODEL=NousResearch/Llama-2-7b-chat-hf
    commands:
      - uv pip install vllm
      - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
    port: 8000

    resources:
      gpu: 24GB
    ```

    </div>

??? info "Private repos"
    If a Git repo is private, `dstack` will automatically try to use your default Git credentials (from
    `~/.ssh/config` or `~/.config/gh/hosts.yml`).

    If you want to use custom credentials, you can provide them with [`dstack init`](../reference/cli/dstack/init.md).

> Currently, you can configure up to one repo per run configuration.

### Retry policy

By default, if `dstack` can't find capacity, or the service exits with an error, or the instance is interrupted, the run will fail.

If you'd like `dstack` to automatically retry, configure the 
[retry](../reference/dstack.yml/service.md#retry) property accordingly:
<!-- TODO: Add a relevant example -->

<div editor-title=".dstack.yml">

```yaml
type: service
image: my-app:latest
port: 80

retry:
  on_events: [no-capacity, error, interruption]
  # Retry for up to 1 hour
  duration: 1h
```

</div>

If one replica of a multi-replica service fails with retry enabled,
`dstack` will resubmit only the failed replica while keeping active replicas running.

### Spot policy

By default, `dstack` uses on-demand instances. However, you can change that
via the [`spot_policy`](../reference/dstack.yml/service.md#spot_policy) property. It accepts `spot`, `on-demand`, and `auto`.

### Utilization policy

Sometimes it’s useful to track whether a service is fully utilizing all GPUs. While you can check this with
[`dstack metrics`](../reference/cli/dstack/metrics.md), `dstack` also lets you set a policy to auto-terminate the run if any GPU is underutilized.

Below is an example of a service that auto-terminate if any GPU stays below 10% utilization for 1 hour.

<!-- TODO: Add a relevant example -->

<div editor-title=".dstack.yml">

```yaml
type: service
name: llama-2-7b-service

python: 3.12
env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - uv pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB

utilization_policy:
  min_gpu_utilization: 10
  time_window: 1h
```

</div>

### Schedule

Specify `schedule` to start a service periodically at specific UTC times using the cron syntax:

<div editor-title=".dstack.yml">

```yaml
type: service
name: llama-2-7b-service

python: 3.12
env:
  - HF_TOKEN
  - MODEL=NousResearch/Llama-2-7b-chat-hf
commands:
  - uv pip install vllm
  - python -m vllm.entrypoints.openai.api_server --model $MODEL --port 8000
port: 8000

resources:
  gpu: 24GB

schedule:
  cron: "0 8 * * mon-fri" # at 8:00 UTC from Monday through Friday
```

</div>

The `schedule` property can be combined with `max_duration` or `utilization_policy` to shutdown the service automatically when it's not needed.

??? info "Cron syntax"
    `dstack` supports [POSIX cron syntax](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/crontab.html#tag_20_25_07). One exception is that days of the week are started from Monday instead of Sunday so `0` corresponds to Monday.
    
    The month and day of week fields accept abbreviated English month and weekday names (`jan–dec` and `mon–sun`) respectively.

    A cron expression consists of five fields:

    ```
    ┌───────────── minute (0-59)
    │ ┌───────────── hour (0-23)
    │ │ ┌───────────── day of the month (1-31)
    │ │ │ ┌───────────── month (1-12 or jan-dec)
    │ │ │ │ ┌───────────── day of the week (0-6 or mon-sun)
    │ │ │ │ │
    │ │ │ │ │
    │ │ │ │ │
    * * * * *
    ```

    The following operators can be used in any of the fields:

    | Operator | Description           | Example                                                                 |
    |----------|-----------------------|-------------------------------------------------------------------------|
    | `*`      | Any value             | `0 * * * *` runs every hour at minute 0                                 |
    | `,`      | Value list separator  | `15,45 10 * * *` runs at 10:15 and 10:45 every day.                     |
    | `-`      | Range of values       | `0 1-3 * * *` runs at 1:00, 2:00, and 3:00 every day.                   |
    | `/`      | Step values           | `*/10 8-10 * * *` runs every 10 minutes during the hours 8:00 to 10:59. |

--8<-- "docs/concepts/snippets/manage-fleets.ext"

!!! info "Reference"
    Services support many more configuration options,
    incl. [`backends`](../reference/dstack.yml/service.md#backends), 
    [`regions`](../reference/dstack.yml/service.md#regions), 
    [`max_price`](../reference/dstack.yml/service.md#max_price), and
    among [others](../reference/dstack.yml/service.md).

## Rolling deployment

To deploy a new version of a service that is already `running`, use `dstack apply`. `dstack` will automatically detect changes and suggest a rolling deployment update.

<div class="termy">

```shell
$ dstack apply -f my-service.dstack.yml

Active run my-service already exists. Detected changes that can be updated in-place:
- Repo state (branch, commit, or other)
- File archives
- Configuration properties:
  - env
  - files

Update the run? [y/n]:
```

</div>

If approved, `dstack` gradually updates the service replicas. To update a replica, `dstack` starts a new replica, waits for it to become `running` and for all of its [probes](#probes) to pass, then terminates the old replica. This process is repeated for each replica, one at a time.

You can track the progress of rolling deployment in both `dstack apply` or `dstack ps`. 
Older replicas have lower `deployment` numbers; newer ones have higher.

<!--
    Not using termy for this example, since the example shows an intermediate CLI state,
    not a completed command.
-->

```shell
$ dstack apply -f my-service.dstack.yml

⠋ Launching my-service...
 NAME                            BACKEND          PRICE    STATUS       SUBMITTED
 my-service deployment=1                                   running      11 mins ago
   replica=0 job=0 deployment=0  aws (us-west-2)  $0.0026  terminating  11 mins ago
   replica=1 job=0 deployment=1  aws (us-west-2)  $0.0026  running      1 min ago
```

The rolling deployment stops when all replicas are updated or when a new deployment is submitted.

??? info "Supported properties"
    <!-- NOTE: should be in sync with constants in server/services/runs.py -->

    Rolling deployment supports changes to the following properties: `port`, `probes`, `resources`, `volumes`, `docker`, `files`, `image`, `user`, `privileged`, `entrypoint`, `working_dir`, `python`, `nvcc`, `single_branch`, `env`, `shell`, `commands`, as well as changes to [repo](#repos) or [file](#files) contents.

    Changes to `replicas` and `scaling` can be applied without redeploying replicas.

    Changes to other properties require a full service restart.

    To trigger a rolling deployment when no properties have changed (e.g., after updating [secrets](secrets.md) or to restart all replicas),  
    make a minor config change, such as adding a dummy [environment variable](#environment-variables).

--8<-- "docs/concepts/snippets/manage-runs.ext"

!!! info "What's next?"
    1. Read about [dev environments](dev-environments.md) and [tasks](tasks.md)
    2. Learn how to manage [fleets](fleets.md)
    3. See how to set up [gateways](gateways.md)
    4. Check the [TGI :material-arrow-top-right-thin:{ .external }](../../examples/inference/tgi/index.md){:target="_blank"},
       [vLLM :material-arrow-top-right-thin:{ .external }](../../examples/inference/vllm/index.md){:target="_blank"}, and 
       [NIM :material-arrow-top-right-thin:{ .external }](../../examples/inference/nim/index.md){:target="_blank"} examples
