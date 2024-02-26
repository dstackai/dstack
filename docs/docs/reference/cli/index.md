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

This command initializes the current folder as a repo.

<div class="termy">

```shell
$ dstack init --help
#GENERATE#
```

</div>

??? info "Git credentials"

    If the current folder is a Git repo, the command authorizes `dstack` to access it.
    By default, the command uses the default Git credentials configured for the repo. 
    You can override these credentials via `--token` (OAuth token) or `--git-identity`.

??? info "Custom SSH key"

    By default, this command generates an SSH key that will be used for port forwarding and SSH access to running workloads. 
    You can override this key via `--ssh-identity`.

### dstack run

This command runs a given configuration.

<div class="termy">

```shell
$ dstack run . --help
#GENERATE#
```

</div>

??? info ".gitignore"
    When running anything via CLI, `dstack` uses the exact version of code from your project directory.

    If there are large files, consider creating a `.gitignore` file to exclude them for better performance.

### dstack ps

This command shows the status of runs.

<div class="termy">

```shell
$ dstack ps --help
#GENERATE#
```

</div>

### dstack stop

This command stops run(s) within the current repository.

<div class="termy">

```shell
$ dstack stop --help
#GENERATE#
```

</div>

### dstack logs

This command shows the output of a given run within the current repository.

<div class="termy">

```shell
$ dstack logs --help
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

### dstack pool

Pools allow for managing the lifecycle of instances and reusing them across runs. 
The default pool is created automatically.

##### dstack pool add

The `dstack pool add` command adds an instance to a pool. If no pool name is specified, the instance goes to the default pool.

<div class="termy">

```shell
$ dstack pool add --help
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

##### dstack pool create

The `dstack pool create` command creates a new pool.

<div class="termy">

```shell
$ dstack pool create --help
#GENERATE#
```

</div>

##### dstack pool list

The `dstack pool delete` lists all existing pools.

<div class="termy">

```shell
$ dstack pool delete --help
#GENERATE#
```

</div>

##### dstack pool delete

The `dstack pool delete` command deletes a specified pool.

<div class="termy">

```shell
$ dstack gateway update --help
#GENERATE#
```

</div>

### dstack gateway

A gateway is required for running services. It handles ingress traffic, authentication, domain mapping, model mapping
for the OpenAI-compatible endpoint, and so on.

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

## Environment variables

| Name                              | Description                                   | Default            |
|-----------------------------------|-----------------------------------------------|--------------------|
| `DSTACK_CLI_LOG_LEVEL`            | Configures CLI logging level                  | `CRITICAL`         |
| `DSTACK_PROFILE`                  | Has the same effect as `--profile`            | `None`             |
| `DSTACK_PROJECT`                  | Has the same effect as `--project`            | `None`             |
| `DSTACK_DEFAULT_CREDS_DISABLED`   | Disables default credentials detection if set | `None`             |
| `DSTACK_LOCAL_BACKEND_ENABLED`    | Enables local backend for debug if set        | `None`             |
| `DSTACK_RUNNER_VERSION`           | Sets exact runner version for debug           | `latest`           |
| `DSTACK_SERVER_ADMIN_TOKEN`       | Has the same effect as `--token`              | `None`             |
| `DSTACK_SERVER_DIR`               | Sets path to store data and server configs    | `~/.dstack/server` |
| `DSTACK_SERVER_HOST`              | Has the same effect as `--host`               | `127.0.0.1`        |
| `DSTACK_SERVER_LOG_LEVEL`         | Has the same effect as `--log-level`          | `WARNING`          |
| `DSTACK_SERVER_PORT`              | Has the same effect as `--port`               | `3000`             |
| `DSTACK_SERVER_ROOT_LOG_LEVEL`    | Sets root logger log level                    | `ERROR`            |
| `DSTACK_SERVER_UVICORN_LOG_LEVEL` | Sets uvicorn logger log level                 | `ERROR`            |