# CLI

## Commands

### dstack server

This command starts the `dstack` server.

<div class="termy">

```shell
$ dstack server --help
#GENERATE#
```

</div>

[//]: # (DSTACK_SERVER_ENVIRONMENT, DSTACK_SERVER_CONFIG_DISABLED, DSTACK_SENTRY_DSN, DSTACK_SENTRY_TRACES_SAMPLE_RATE, DSTACK_SERVER_BUCKET_REGION, DSTACK_SERVER_BUCKET, DSTACK_ALEMBIC_MIGRATIONS_LOCATION)

### dstack init

This command must be called inside a folder before you can run `dstack apply`.

**Git credentials**

If the current folder is a remote Git repository, `dstack init` ensures that `dstack` can access it.
By default, the command uses the remote repo's default Git credentials. These can be overridden with 
`--git-identity` (private SSH key) or `--token` (OAuth token).

<div class="termy">

```shell
$ dstack init --help
#GENERATE#
```

</div>

**User SSH key**

By default, `dstack` uses its own SSH key to access instances (`~/.dstack/ssh/id_rsa`). 
It is possible to override this key via the `--ssh-identity` argument.

### dstack apply

This command applies a given configuration. If a resource does not exist, `dstack apply` creates the resource.
If a resource exists, `dstack apply` updates the resource in-place or re-creates the resource if the update is not possible.

<div class="termy">

```shell
$ dstack apply --help
#GENERATE#
```

</div>

### dstack delete

This command deletes the resources defined by a given configuration.

<div class="termy">

```shell
$ dstack delete --help
#GENERATE#
```

</div>

### dstack ps

This command shows the status of runs.

<div class="termy">

```shell
$ dstack ps --help
#GENERATE#
```

</div>

### dstack stop

This command stops run(s).

<div class="termy">

```shell
$ dstack stop --help
#GENERATE#
```

</div>

### dstack attach

This command attaches to a given run. It establishes the SSH tunnel, forwards ports, and shows real-time run logs.

<div class="termy">

```shell
$ dstack attach --help
#GENERATE#
```

</div>

### dstack logs

This command shows the output of a given run.

<div class="termy">

```shell
$ dstack logs --help
#GENERATE#
```

</div>

### dstack stats

This command shows run hardware metrics such as CPU, memory, and GPU utilization.

<div class="termy">

```shell
$ dstack stats --help
#GENERATE#
```

</div>

### dstack config

Both the CLI and API need to be configured with the server address, user token, and project name
via `~/.dstack/config.yml`.

At startup, the server automatically configures CLI and API with the server address, user token, and
the default project name (`main`). This configuration is stored via `~/.dstack/config.yml`.

To use CLI and API on different machines or projects, use the `dstack config` command.

<div class="termy">

```shell
$ dstack config --help
#GENERATE#
```

</div>

### dstack fleet

Fleets enable efficient provisioning and management of clusters and instances.

##### dstack fleet list

The `dstack fleet list` command displays fleets and instances.

<div class="termy">

```shell
$ dstack fleet list --help
#GENERATE#
```

</div>

##### dstack fleet delete

The `dstack fleet delete` deletes fleets and instances.
Cloud instances are terminated upon deletion.

<div class="termy">

```shell
$ dstack fleet delete --help
#GENERATE#
```

</div>

### dstack gateway

A gateway allows publishing services at a custom domain with HTTPS.

##### dstack gateway list

The `dstack gateway list` command displays the names and addresses of the gateways configured in the project.

<div class="termy">

```shell
$ dstack gateway list --help
#GENERATE#
```

</div>

##### dstack gateway create

The `dstack gateway create` command creates a new gateway instance in the project.

<div class="termy">

```shell
$ dstack gateway create --help
#GENERATE#
```

</div>

##### dstack gateway delete

The `dstack gateway delete` command deletes the specified gateway.

<div class="termy">

```shell
$ dstack gateway delete --help
#GENERATE#
```

</div>

##### dstack gateway update

The `dstack gateway update` command updates the specified gateway.

<div class="termy">

```shell
$ dstack gateway update --help
#GENERATE#
```

</div>

### dstack volume

The volumes commands.

##### dstack volume list

The `dstack volume list` command lists volumes.

<div class="termy">

```shell
$ dstack volume list --help
#GENERATE#
```

</div>

##### dstack volume delete

The `dstack volume delete` command deletes volumes.

<div class="termy">

```shell
$ dstack volume delete --help
#GENERATE#
```

</div>

### dstack run

This command runs a given configuration.

!!! warning "Deprecation"
    `dstack run` is deprecated in favor of `dstack apply`.

<div class="termy">

```shell
$ dstack run . --help
#GENERATE#
```

</div>

??? info ".gitignore"
    When running anything via CLI, `dstack` uses the exact version of code from your project directory.

    If there are large files, consider creating a `.gitignore` file to exclude them for better performance.


### dstack pool

Pools allow for managing the lifecycle of instances and reusing them across runs. 
The default pool is created automatically.

!!! warning "Deprecation"
    Pools are deprecated in favor of fleets and will be removed in 0.19.0.

##### dstack pool add

The `dstack pool add` command provisions a cloud instance and adds it to a pool. If no pool name is specified, the instance goes to the default pool.

<div class="termy">

```shell
$ dstack pool add --help
#GENERATE#
```

</div>

##### dstack pool add-ssh

The `dstack pool add-ssh` command adds an existing remote instance to a pool.
If no pool name is specified, the instance goes to the default pool.

<div class="termy">

```shell
$ dstack pool add-ssh --help
#GENERATE#
```

</div>

##### dstack pool ps

The `dstack pool ps` command lists all active instances of a pool.
If no pool name is specified, default pool instances are displayed.

<div class="termy">

```shell
$ dstack pool ps --help
#GENERATE#
```

</div>

##### dstack pool rm

The `dstack pool rm` command removes an instance from a pool.
Cloud instances are terminated upon removal.

<div class="termy">

```shell
$ dstack pool rm --help
#GENERATE#
```

</div>

##### dstack pool create

The `dstack pool create` command creates a new pool.

<div class="termy">

```shell
$ dstack pool create --help
#GENERATE#
```

</div>

##### dstack pool list

The `dstack pool list` command lists all existing pools.

<div class="termy">

```shell
$ dstack pool list --help
#GENERATE#
```

</div>

##### dstack pool set-default

The `dstack pool set-default` command sets the project's default pool.

<div class="termy">

```shell
$ dstack pool set-default --help
#GENERATE#
```

</div>

##### dstack pool delete

The `dstack pool delete` command deletes a specified pool.

<div class="termy">

```shell
$ dstack pool delete --help
#GENERATE#
```

</div>

## Environment variables

 * `DSTACK_CLI_LOG_LEVEL` – (Optional) Configures CLI logging level. Defaults to `INFO`.
 * `DSTACK_SERVER_LOG_LEVEL` – (Optional) Has the same effect as `--log-level`. Defaults to `INFO`.
 * `DSTACK_SERVER_HOST` – (Optional) Has the same effect as `--host`. Defaults to `127.0.0.1`.
 * `DSTACK_SERVER_PORT` – (Optional) Has the same effect as `--port`. Defaults to `3000`.
 * `DSTACK_SERVER_ADMIN_TOKEN` – (Optional) Has the same effect as `--token`. Defaults to `None`.
 * `DSTACK_DATABASE_URL` – (Optional) The database URL to use instead of default SQLite. Currently `dstack` supports Postgres. Example: `postgresql+asyncpg://myuser:mypassword@localhost:5432/mydatabase`. Defaults to `None`.
 * `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP` – (Optional) The CloudWatch Logs group for workloads logs. If not set, the default file-based log storage is used.
 * `DSTACK_SERVER_CLOUDWATCH_LOG_REGION` — (Optional) The CloudWatch Logs region. Defaults to `None`.
 * `DSTACK_DEFAULT_SERVICE_CLIENT_MAX_BODY_SIZE` – (Optional) Request body size limit for services, in bytes. Defaults to 64 MiB.
 * `DSTACK_FORBID_SERVICES_WITHOUT_GATEWAY` - (Optional) Forbids registering new services without a gateway if set to any value.
 * `DSTACK_SERVER_DIR` – (Optional) Sets path to store data and server configs. Defaults to `~/.dstack/server`.

??? info "Internal environment variables"
     * `DSTACK_SERVER_ROOT_LOG_LEVEL` – (Optional) Sets root logger log level. Defaults to `ERROR`.
     * `DSTACK_SERVER_LOG_FORMAT` – (Optional) Sets format of log output. Can be `rich`, `standard`, `json`. Defaults to `rich`.
     * `DSTACK_SERVER_UVICORN_LOG_LEVEL` – (Optional) Sets uvicorn logger log level. Defaults to `ERROR`.
     * `DSTACK_PROFILE` – (Optional) Has the same effect as `--profile`. Defaults to `None`.
     * `DSTACK_PROJECT` – (Optional) Has the same effect as `--project`. Defaults to `None`.
     * `DSTACK_RUNNER_VERSION` – (Optional) Sets exact runner version for debug. Defaults to `latest`. Ignored if `DSTACK_RUNNER_DOWNLOAD_URL` is set.
     * `DSTACK_RUNNER_DOWNLOAD_URL` – (Optional) Overrides `dstack-runner` binary download URL.
     * `DSTACK_SHIM_DOWNLOAD_URL` – (Optional) Overrides `dstack-shim` binary download URL.
     * `DSTACK_DEFAULT_CREDS_DISABLED` – (Optional) Disables default credentials detection if set. Defaults to `None`.
     * `DSTACK_LOCAL_BACKEND_ENABLED` – (Optional) Enables local backend for debug if set. Defaults to `None`.
