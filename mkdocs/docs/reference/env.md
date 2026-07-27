# Environment variables

## .dstack.yml

The following read-only environment variables are automatically propagated to configurations for dev environments,
tasks, and services:

- `DSTACK_RUN_NAME`{ #DSTACK_RUN_NAME } – The name of the run.

     The example below simply prints `vscode` to the output.

     ```yaml
     type: task
     name: vscode

     commands:
       - echo $DSTACK_RUN_NAME
     ```

     If `name` is not set in the configuration, it is assigned a random name (e.g. `wet-mangust-1`).

- `DSTACK_RUN_ID`{ #DSTACK_RUN_ID } – The UUID of the run.
- `DSTACK_JOB_ID`{ #DSTACK_JOB_ID } – The UUID of the job submission.
- `DSTACK_REPO_ID`{ #DSTACK_REPO_ID } – The ID of the repo.
- `DSTACK_GPUS_NUM`{ #DSTACK_GPUS_NUM } – The total number of GPUs in the run.

     Example:

     ```yaml
     type: service
     name: llama31

     env:
       - HF_TOKEN
     commands:
       - pip install vllm
       - vllm serve meta-llama/Meta-Llama-3.1-8B-Instruct
         --max-model-len 4096
         --tensor-parallel-size $DSTACK_GPUS_NUM
     port: 8000
     model: meta-llama/Meta-Llama-3.1-8B-Instruct

     resources:
       gpu: 24GB
     ```

- `DSTACK_NODES_NUM`{ #DSTACK_NODES_NUM } – The number of nodes in the run
- `DSTACK_GPUS_PER_NODE`{ #DSTACK_GPUS_PER_NODE } – The number of GPUs per node
- `DSTACK_NODE_RANK`{ #DSTACK_NODE_RANK } – The rank of the node
- `DSTACK_MASTER_NODE_IP`{ #DSTACK_NODE_RANK } – The internal IP address of the master node.

     Below is an example of using `DSTACK_NODES_NUM`, `DSTACK_GPUS_PER_NODE`, `DSTACK_NODE_RANK`, and `DSTACK_MASTER_NODE_IP`
     for distributed training:

     ```yaml
      type: task
      name: train-distrib

      # The size of the cluster
      nodes: 2

      python: 3.12
      env:
        - NCCL_DEBUG=INFO
      commands:
        - git clone https://github.com/pytorch/examples.git pytorch-examples
        - cd pytorch-examples/distributed/ddp-tutorial-series
        - uv pip install -r requirements.txt
        - |
          torchrun \
            --nproc-per-node=$DSTACK_GPUS_PER_NODE \
            --node-rank=$DSTACK_NODE_RANK \
            --nnodes=$DSTACK_NODES_NUM \
            --master-addr=$DSTACK_MASTER_NODE_IP \
            --master-port=12345 \
            multinode.py 50 10

      resources:
        gpu: 24GB:1..2
        # Uncomment if using multiple GPUs
        #shm_size: 24GB
     ```

- `DSTACK_NODES_IPS`{ #DSTACK_NODES_IPS } – The list of internal IP addresses of all nodes delimited by `"\n"`.
- `DSTACK_MPI_HOSTFILE`{ #DSTACK_MPI_HOSTFILE } – The path to a pre-populated MPI hostfile that can be used directly as `mpirun --hostfile $DSTACK_MPI_HOSTFILE`.

## Server

The following environment variables are supported by the `dstack` server and can be specified whether the server is run
via `dstack server` or deployed using Docker.

For more details on the options below, refer to the [server deployment](../guides/server-deployment.md) guide.

- `DSTACK_SERVER_LOG_LEVEL`{ #DSTACK_SERVER_LOG_LEVEL } – Has the same effect as `--log-level`. Defaults to `INFO`.

     Example:

     <div class="termy">

     ```shell
     $ DSTACK_SERVER_LOG_LEVEL=debug dstack server
     ```

     </div>

- `DSTACK_SERVER_LOG_FORMAT`{ #DSTACK_SERVER_LOG_FORMAT } – Sets format of log output. Can be `rich`, `standard`, `json`. Defaults to `rich`.
- `DSTACK_SERVER_HOST`{ #DSTACK_SERVER_HOST } – Has the same effect as `--host`. Defaults to `127.0.0.1`.
- `DSTACK_SERVER_PORT`{ #DSTACK_SERVER_PORT } – Has the same effect as `--port`. Defaults to `3000`.
- `DSTACK_SERVER_URL`{ #DSTACK_SERVER_URL } – The URL that the server is running on, e.g. `https://my-server.dstack.ai` Defaults to `http://{DSTACK_SERVER_HOST}:{DSTACK_SERVER_PORT}`.
- `DSTACK_SERVER_ADMIN_TOKEN`{ #DSTACK_SERVER_ADMIN_TOKEN } – Has the same effect as `--token`. Defaults to `None`.
- `DSTACK_SERVER_DIR`{ #DSTACK_SERVER_DIR } – Sets path to store data and server configs. Defaults to `~/.dstack/server`.
- `DSTACK_DATABASE_URL`{ #DSTACK_DATABASE_URL } – The database URL to use instead of default SQLite. Currently `dstack` supports Postgres. Example: `postgresql+asyncpg://myuser:mypassword@localhost:5432/mydatabase`. Defaults to `None`.
- `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP`{ #DSTACK_SERVER_CLOUDWATCH_LOG_GROUP } – The CloudWatch Logs group for storing workloads logs. If not set, the default file-based log storage is used.
- `DSTACK_SERVER_CLOUDWATCH_LOG_REGION`{ #DSTACK_SERVER_CLOUDWATCH_LOG_REGION } – The CloudWatch Logs region. Defaults to `None`.
- `DSTACK_SERVER_GCP_LOGGING_PROJECT`{ #DSTACK_SERVER_GCP_LOGGING_PROJECT } – The GCP Logging project for storing workloads logs. If not set, the default file-based log storage is used.
- `DSTACK_SERVER_FLUENTBIT_HOST`{ #DSTACK_SERVER_FLUENTBIT_HOST } – The Fluent-bit host for log forwarding. If set, enables Fluent-bit log storage.
- `DSTACK_SERVER_FLUENTBIT_PORT`{ #DSTACK_SERVER_FLUENTBIT_PORT } – The Fluent-bit port. Defaults to `24224`.
- `DSTACK_SERVER_FLUENTBIT_PROTOCOL`{ #DSTACK_SERVER_FLUENTBIT_PROTOCOL } – The protocol to use: `forward` or `http`. Defaults to `forward`.
- `DSTACK_SERVER_FLUENTBIT_TAG_PREFIX`{ #DSTACK_SERVER_FLUENTBIT_TAG_PREFIX } – The tag prefix for logs. Defaults to `dstack`.
- `DSTACK_SERVER_ELASTICSEARCH_HOST`{ #DSTACK_SERVER_ELASTICSEARCH_HOST } – The Elasticsearch/OpenSearch host for reading logs back through dstack. Optional; if not set, Fluent-bit runs in ship-only mode (logs are forwarded but not readable through dstack UI/CLI).
- `DSTACK_SERVER_ELASTICSEARCH_INDEX`{ #DSTACK_SERVER_ELASTICSEARCH_INDEX } – The Elasticsearch/OpenSearch index pattern. Defaults to `dstack-logs`.
- `DSTACK_SERVER_ELASTICSEARCH_API_KEY`{ #DSTACK_SERVER_ELASTICSEARCH_API_KEY } – The Elasticsearch/OpenSearch API key for authentication.
- `DSTACK_ENABLE_PROMETHEUS_METRICS`{ #DSTACK_ENABLE_PROMETHEUS_METRICS } — Enables Prometheus metrics collection and export.
- `DSTACK_SENTRY_DSN`{ #DSTACK_SENTRY_DSN } – The Sentry DSN. If set, enables error reporting and tracing via the Sentry SDK. See [observability](../guides/server-deployment.md#observability).
- `DSTACK_SENTRY_TRACES_SAMPLE_RATE`{ #DSTACK_SENTRY_TRACES_SAMPLE_RATE } – The Sentry sample rate for API request traces. Defaults to `0.1`.
- `DSTACK_SENTRY_TRACES_BACKGROUND_SAMPLE_RATE`{ #DSTACK_SENTRY_TRACES_BACKGROUND_SAMPLE_RATE } – The Sentry sample rate for background task traces. Defaults to `0.01`.
- `DSTACK_SENTRY_PROFILES_SAMPLE_RATE`{ #DSTACK_SENTRY_PROFILES_SAMPLE_RATE } – The Sentry profiling sample rate, relative to the traces sample rate. Defaults to `0`.
- `DSTACK_OTEL_TRACES_ENABLED`{ #DSTACK_OTEL_TRACES_ENABLED } – Enables OpenTelemetry tracing if set to any value. Requires the `otel` extra. The exporter is configured via standard `OTEL_*` env vars such as `OTEL_EXPORTER_OTLP_ENDPOINT`. See [observability](../guides/server-deployment.md#observability).
- `DSTACK_OTEL_TRACES_SAMPLE_RATE`{ #DSTACK_OTEL_TRACES_SAMPLE_RATE } – The head sampling rate for API request traces. Defaults to `1.0`, which assumes sampling is done downstream, e.g. in an OTel collector.
- `DSTACK_OTEL_TRACES_BACKGROUND_SAMPLE_RATE`{ #DSTACK_OTEL_TRACES_BACKGROUND_SAMPLE_RATE } – The head sampling rate for background task traces. Defaults to `1.0`.
- `DSTACK_OTEL_LOGS_ENABLED`{ #DSTACK_OTEL_LOGS_ENABLED } – Enables server log export via OTLP if set to any value. Requires the `otel` extra.
- `DSTACK_OTEL_METRICS_ENABLED`{ #DSTACK_OTEL_METRICS_ENABLED } – Enables OpenTelemetry metrics if set to any value. Requires the `otel` extra.
- `DSTACK_OTEL_METRICS_EXPORTERS`{ #DSTACK_OTEL_METRICS_EXPORTERS } – A comma-separated list of OpenTelemetry metrics exporters: `otlp` (push via OTLP) and/or `prometheus` (expose on the `/metrics` endpoint). Defaults to `otlp`.
- `DSTACK_DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE`{ #DSTACK_DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE } – Request body size limit for services running with a gateway, in bytes. Defaults to 64 MiB.
- `DSTACK_SERVICE_CLIENT_TIMEOUT`{ #DSTACK_SERVICE_CLIENT_TIMEOUT } – Timeout in seconds for HTTP requests sent from the in-server proxy and gateways to service replicas. Defaults to 60.
- `DSTACK_FORBID_SERVICES_WITHOUT_GATEWAY`{ #DSTACK_FORBID_SERVICES_WITHOUT_GATEWAY } – Forbids registering new services without a gateway if set to any value.
- `DSTACK_FORBID_DSTACK_IN_RUNS`{ #DSTACK_FORBID_DSTACK_IN_RUNS } – Forbids submitting runs with `dstack: true` (dstack server access inside runs) if set to any value.
- `DSTACK_SERVER_CODE_UPLOAD_LIMIT`{ #DSTACK_SERVER_CODE_UPLOAD_LIMIT } - The repo size limit when uploading diffs or local repos, in bytes. Set to `0` to disable size limits. Defaults to `2MiB`.
- `DSTACK_SERVER_S3_BUCKET`{ #DSTACK_SERVER_S3_BUCKET } - The bucket that repo diffs will be uploaded to if set. If unset, diffs are uploaded to the database.
- `DSTACK_SERVER_S3_BUCKET_REGION`{ #DSTACK_SERVER_S3_BUCKET_REGION } - The region of the S3 Bucket.
- `DSTACK_SERVER_GCS_BUCKET`{ #DSTACK_SERVER_GCS_BUCKET } - The bucket that repo diffs will be uploaded to if set. If unset, diffs are uploaded to the database.
- `DSTACK_DB_POOL_SIZE`{ #DSTACK_DB_POOL_SIZE } - The client DB connections pool size. Defaults to `20`,
- `DSTACK_DB_MAX_OVERFLOW`{ #DSTACK_DB_MAX_OVERFLOW } - The client DB connections pool allowed overflow. Defaults to `20`.
- `DSTACK_SERVER_BACKGROUND_PROCESSING_DISABLED`{ #DSTACK_SERVER_BACKGROUND_PROCESSING_DISABLED } - Disables background processing if set to any value. Useful to run only web frontend and API server.
- `DSTACK_SERVER_MAX_PROBES_PER_JOB`{ #DSTACK_SERVER_MAX_PROBES_PER_JOB } - Maximum number of probes allowed in a run configuration. Validated at apply time.
- `DSTACK_SERVER_MAX_PROBE_TIMEOUT`{ #DSTACK_SERVER_MAX_PROBE_TIMEOUT } - Maximum allowed timeout for a probe. Validated at apply time.
- `DSTACK_SERVER_METRICS_RUNNING_TTL_SECONDS`{ #DSTACK_SERVER_METRICS_RUNNING_TTL_SECONDS } – Maximum age of metrics samples for running jobs.
- `DSTACK_SERVER_METRICS_FINISHED_TTL_SECONDS`{ #DSTACK_SERVER_METRICS_FINISHED_TTL_SECONDS } – Maximum age of metrics samples for finished jobs.
- `DSTACK_SERVER_INSTANCE_HEALTH_TTL_SECONDS`{ #DSTACK_SERVER_INSTANCE_HEALTH_TTL_SECONDS } – Maximum age of instance health checks.
- `DSTACK_SERVER_INSTANCE_HEALTH_MIN_COLLECT_INTERVAL_SECONDS`{ #DSTACK_SERVER_INSTANCE_HEALTH_MIN_COLLECT_INTERVAL_SECONDS } – Minimum time interval between consecutive health checks of the same instance.
- `DSTACK_SERVER_EVENTS_TTL_SECONDS`{ #DSTACK_SERVER_EVENTS_TTL_SECONDS } - Maximum age of event records. Set to `0` to disable event storage. Defaults to 30 days.
- `DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY`{ #DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY } – A default Docker registry to use for job images that do not specify an explicit registry. E.g., if set to `registry.example`, then `image: ubuntu` becomes equivalent to `image: registry.example/ubuntu`. **Note**: This setting should only be used for configuring registries that act as a pull-through cache for Docker Hub. The default `dstack` images are also pulled from the configured registry.
- `DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY_USERNAME`{ #DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY_USERNAME } – Username for authenticating with the default Docker registry. See `DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD`.
- `DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD`{ #DSTACK_SERVER_DEFAULT_DOCKER_REGISTRY_PASSWORD } – Password for authenticating with the default Docker registry. Applied only when the image has no explicit registry and the run configuration does not specify `registry_auth`. **Note**: The value may be visible to anyone who can SSH into instances managed by `dstack`, which usually includes all users of that `dstack` server.
- `DSTACK_SSHPROXY_API_TOKEN`{ #DSTACK_SSHPROXY_API_TOKEN } – Authentication token for the SSH proxy API. Required to enable SSH proxy integration; must match the token configured when deploying [`dstack-sshproxy`](https://github.com/dstackai/sshproxy).
- `DSTACK_SERVER_SSHPROXY_ADDRESS`{ #DSTACK_SERVER_SSHPROXY_ADDRESS } – Address of the SSH proxy exposed to users, in `HOSTNAME[:PORT]` form. `PORT` defaults to `22` if omitted. Required together with `DSTACK_SSHPROXY_API_TOKEN` to enable SSH proxy integration.
- `DSTACK_SERVER_SSHPROXY_ENFORCED`{ #DSTACK_SERVER_SSHPROXY_ENFORCED } – When set to any value, restricts all SSH connections to go through the SSH proxy.
- `DSTACK_SERVER_JOB_NETWORK_MODE`{ #DSTACK_SERVER_JOB_NETWORK_MODE } – Controls the network mode assigned to jobs. Accepts an integer value: `1` forces bridge networking for single-node jobs while distributed tasks still use host networking; `2` uses host networking whenever the job occupies a full instance (default); `3` forces bridge networking for all jobs including distributed tasks.
- `DSTACK_SERVER_SSH_CONNECT_TIMEOUT`{ #DSTACK_SERVER_SSH_CONNECT_TIMEOUT } – The SSH `ConnectTimeout` for server-instance connections, in seconds. Defaults to `3`. Increase if there are high-latency links between the server and instances.
- `DSTACK_SERVER_SSH_POOL_DISABLED`{ #DSTACK_SERVER_SSH_POOL_DISABLED } – Disables the reuse of server SSH connections to instances. If set, significantly decreases server RAM usage, but
slows down processing and may cause CPU spikes due to frequent SSH-connection establishment.

??? info "Internal environment variables"
     The following environment variables are intended for development purposes:

     * `DSTACK_SERVER_ROOT_LOG_LEVEL` – Sets root logger log level. Defaults to `ERROR`.
     * `DSTACK_SERVER_UVICORN_LOG_LEVEL` – Sets uvicorn logger log level. Defaults to `ERROR`.
     * `DSTACK_SERVER_MAX_OFFERS_TRIED` - Sets how many instance offers to try when starting a job.
       Setting a high value can degrade server performance.
     * `DSTACK_RUNNER_VERSION` – Sets exact runner version for debug. Defaults to `latest`. Ignored if `DSTACK_RUNNER_DOWNLOAD_URL` is set.
     * `DSTACK_RUNNER_DOWNLOAD_URL` – Overrides `dstack-runner` binary download URL. The URL can contain `{version}` and/or `{arch}` placeholders,
      where `{version}` is `dstack` version in the `X.Y.Z` format or `latest`, and `{arch}` is either `amd64` or `arm64`, for example,
      `https://dstack.example.com/{arch}/{version}/dstack-runner`.
     * `DSTACK_SHIM_DOWNLOAD_URL` – Overrides `dstack-shim` binary download URL. The URL can contain `{version}` and/or `{arch}` placeholders,
      see `DSTACK_RUNNER_DOWNLOAD_URL` for the details.
     * `DSTACK_DEFAULT_CREDS_DISABLED` – Disables default credentials detection if set. Defaults to `None`.

## CLI

The following environment variables are supported by the CLI.

- `DSTACK_TOKEN`{ #DSTACK_TOKEN } – The user token used by the CLI. Set `DSTACK_TOKEN`,
  `DSTACK_SERVER_URL`, and `DSTACK_PROJECT` together to use the CLI without a project in
  `~/.dstack/config.yml`, or to override the configured server, project, and user.

  ```shell
  DSTACK_SERVER_URL=https://server.example.com \
  DSTACK_PROJECT=main \
  DSTACK_TOKEN=your-token \
  dstack ps
  ```

- `DSTACK_CLI_LOG_LEVEL`{ #DSTACK_CLI_LOG_LEVEL } – Sets the logging level for CLI output to stdout. Defaults to `INFO`.

Example:

<div class="termy">

```shell
$ DSTACK_CLI_LOG_LEVEL=debug dstack apply -f .dstack.yml
```

</div>

- `DSTACK_CLI_FILE_LOG_LEVEL`{ #DSTACK_CLI_FILE_LOG_LEVEL } – Sets the logging level for CLI log files. Defaults to `DEBUG`.

<div class="termy">

```shell
$ find ~/.dstack/logs/cli/

 ~/.dstack/logs/cli/latest.log
 ~/.dstack/logs/cli/2025-07-31.log
```

</div>

- `DSTACK_PROJECT`{ #DSTACK_PROJECT } – Has the same effect as `--project`. Defaults to `None`.
- `DSTACK_AGENT_ANTHROPIC_API_KEY`{ #DSTACK_AGENT_ANTHROPIC_API_KEY } – The Anthropic API key used by the preset agent. If unset, the existing `claude` login is used.
- `DSTACK_AGENT_CLAUDE_PATH`{ #DSTACK_AGENT_CLAUDE_PATH } – The `claude` executable name or path used by the preset agent. Defaults to `claude` from `PATH`.
- `DSTACK_AGENT_ANTHROPIC_MODEL`{ #DSTACK_AGENT_ANTHROPIC_MODEL } – The Claude model used by the preset agent. Defaults to `claude-opus-4-8`.
- `DSTACK_AGENT_CLAUDE_EFFORT`{ #DSTACK_AGENT_CLAUDE_EFFORT } – The Claude effort level used by the preset agent. Can be `low`, `medium`, `high`, `xhigh`, or `max`. If unset, the `claude` CLI default is used.
