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

      nodes: 2
      python: "3.12"

      commands:
        - git clone https://github.com/pytorch/examples.git
        - cd examples/distributed/ddp-tutorial-series
        - pip install -r requirements.txt
        - torchrun
          --nproc-per-node=$DSTACK_GPUS_PER_NODE
          --node-rank=$DSTACK_NODE_RANK
          --nnodes=$DSTACK_NODES_NUM
          --master-addr=$DSTACK_MASTER_NODE_IP
          --master-port=12345
          multinode.py 50 10

      resources:
        gpu: 24GB
        shm_size: 24GB
     ```

- `DSTACK_NODES_IPS`{ #DSTACK_NODES_IPS } – The list of internal IP addresses of all nodes delimited by `"\n"`.

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
- `DSTACK_ENABLE_PROMETHEUS_METRICS`{ #DSTACK_ENABLE_PROMETHEUS_METRICS } — Enables Prometheus metrics collection and export.
- `DSTACK_DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE`{ #DSTACK_DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE } – Request body size limit for services running with a gateway, in bytes. Defaults to 64 MiB.
- `DSTACK_FORBID_SERVICES_WITHOUT_GATEWAY`{ #DSTACK_FORBID_SERVICES_WITHOUT_GATEWAY } – Forbids registering new services without a gateway if set to any value.

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
     * `DSTACK_LOCAL_BACKEND_ENABLED` – Enables local backend for debug if set. Defaults to `None`.

## CLI

The following environment variables are supported by the CLI.

- `DSTACK_CLI_LOG_LEVEL`{ #DSTACK_CLI_LOG_LEVEL } – Configures CLI logging level. Defaults to `INFO`.

Example:

<div class="termy">

```shell
$ DSTACK_CLI_LOG_LEVEL=debug dstack apply -f .dstack.yml
```

</div>

- `DSTACK_PROJECT`{ #DSTACK_PROJECT } – Has the same effect as `--project`. Defaults to `None`.
