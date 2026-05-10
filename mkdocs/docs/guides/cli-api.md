---
title: CLI & API
description: How to use the dstack CLI and HTTP API
---

# CLI & API

!!! info "Prerequisites"
    Ensure the [server](../installation.md#server) is up and running. To use `dstack` with AI agents, install [skills](../installation.md#skills).

The primary way to use `dstack` is the CLI. It can be used to manage
[fleets](../concepts/fleets.md), runs, [volumes](../concepts/volumes.md), and
[gateways](../concepts/gateways.md), view logs, and inspect
[events](../concepts/events.md). Use the HTTP API for functionality not
available in the CLI or for integrations that need to call the server directly.

## CLI

> See [installation](../installation.md#cli) on how to install the CLI.

### Configuration

The CLI requires a [project](../concepts/projects.md) configuration with the project name, server URL, and user token in `~/.dstack/config.yml`.

<div editor-title="~/.dstack/config.yml">

```yaml
projects:
  - name: main
    url: http://127.0.0.1:3000
    token: <user token>
    default: true
  - name: octocat
    url: https://sky.dstack.ai
    token: <user token>
```

</div>

Use [`dstack project`](../reference/cli/dstack/project.md) to list,
[add](../installation.md#configure-the-project), delete, and set the default
project configurations. To run a command against a non-default project, pass
`--project NAME`, or set `DSTACK_PROJECT` in the current shell.

??? info "Projects"
    [Projects](../concepts/projects.md) enable the isolation of different teams and their resources. Users can be added to projects and assigned roles. Each user has a user token for authentication.

### Manage fleets

Before submitting runs, you must create at least one
[fleet](../concepts/fleets.md). Fleets act as both pools of instances and
templates for how those instances are provisioned.

Use [`dstack fleet`](../reference/cli/dstack/fleet.md#dstack-fleet-list) to
list existing fleets, their configurations, and instances (if any):

<div class="termy">

```shell
$ dstack fleet
```

</div>

??? info "Offers"
    Offers are available instance configurations that match resource
    requirements.

    <div class="termy">

    ```shell
    $ dstack offer --gpu H100 --max-offers 10
    ```

    </div>

    If no fleet is specified,
    [`dstack offer`](../reference/cli/dstack/offer.md) shows offers from all
    configured backends.

    Use `--fleet NAME` to restrict offers to a fleet. Listing offers does not
    create capacity.

Define a fleet configuration in a YAML file. The filename must end with
`.dstack.yml`, for example `fleet.dstack.yml`:

<div editor-title="fleet.dstack.yml">

```yaml
type: fleet
name: default

nodes: 0..1
idle_duration: 1h

resources:
  gpu: 0
```

</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f fleet.dstack.yml
```

</div>

If the `nodes` range starts with `0`, `dstack` creates a fleet template.
Instances are provisioned when matching runs are submitted.

### Submit runs

To submit a run, define a
[dev environment](../concepts/dev-environments.md),
[task](../concepts/tasks.md), or [service](../concepts/services.md)
configuration. The example below submits a task.

<div editor-title=".dstack.yml">

```yaml
type: task
name: hello

commands:
  - echo hello world
```

</div>

Submit the run:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml
```

</div>

!!! info "Plan and confirmation"
    `dstack apply` shows the plan and asks for confirmation before submitting
    the run. To only see the plan, answer `n` at the prompt:

    <div class="termy">

    ```shell
    $ echo "n" | dstack apply -f .dstack.yml
    ```

    </div>

    Use `-y` to skip confirmation.

!!! info "Attached by default"
    For run configurations, `dstack apply` automatically attaches after
    submitting the run. This streams logs, forwards declared ports, and
    configures SSH access. See [Attach to runs](#attach-to-runs).

    Use `-d` to submit in detached mode.

### Attach to runs

If the run was submitted with `-d`, or if you need to attach to another job in
a multi-job run, use `dstack attach`:

<div class="termy">

```shell
$ dstack attach &lt;run name&gt;
```

</div>

!!! info "SSH"
    During `dstack apply` in attached mode and during
    `dstack attach <run name>`, the CLI downloads the current user's built-in
    private SSH key if needed and stores it under `~/.dstack/ssh/`.

    While attached, the CLI updates `~/.dstack/ssh/config` with the run name as
    an SSH host alias and ensures this file is included from `~/.ssh/config`:

    <div editor-title="~/.dstack/ssh/config">

    ```ssh-config
    Host &lt;run name&gt;
        HostName localhost
        Port &lt;local SSH port&gt;
        User root
        IdentityFile ~/.dstack/ssh/&lt;key&gt;
        IdentitiesOnly yes
    ```

    </div>

    For VM-based and SSH fleets, `dstack` may also configure the
    `<run name>-host` alias for SSH access to the host.

    While attached, connect to the run with:

    <div class="termy">

    ```shell
    $ ssh &lt;run name&gt;
    ```

    </div>

Use `--job JOB_NUMBER` with `dstack attach` to attach to another job. Ports
declared in the run configuration are forwarded while attached.

??? info "User SSH keys"
    The server stores a built-in SSH key pair for each user.

    Users can add custom public SSH keys via the UI or the
    [users](../reference/http/users.md) API. To use a custom private key for a
    particular run, pass `--ssh-identity` to `dstack apply` or `dstack attach`.

### Browse logs

When `dstack apply` is attached, it streams logs for job `0` automatically.
Use [`dstack logs`](../reference/cli/dstack/logs.md) to view logs in detached
mode, or to view logs for a specific job:

<div class="termy">

```shell
$ dstack logs &lt;run name&gt;
```

</div>

Use `--job JOB_NUMBER` to select a job and `--since` to filter by time.

??? info "Attached logs"
    Use `--logs` with `dstack attach` to stream logs while attaching:

    <div class="termy">

    ```shell
    $ dstack attach &lt;run name&gt; --logs
    ```

    </div>

### Commands

Other common CLI commands include [`dstack ps`](../reference/cli/dstack/ps.md),
[`dstack stop`](../reference/cli/dstack/stop.md), and
[`dstack event`](../reference/cli/dstack/event.md).

!!! info "Verbose and JSON modes"
    Use `-v` for more details where supported. For automation, use `--json`,
    e.g. `dstack ps --json`, `dstack run get <run name> --json`, or
    `dstack fleet get <fleet name> --json`.

## API

The `dstack` API is represented by the HTTP API. Use it for functionality not
available in the CLI or for integrations that need to call the server directly.

<!--
Out of scope for this guide:
- Git repo workflows
- File upload workflows
- Direct SSH/sshproxy workflows
- Backward compatibility between older clients and servers
-->

### Authenticate

The HTTP API requires the `Authorization` header for user authentication:

```text
Authorization: Bearer <user token>
```

### Manage fleets

The [fleets](../reference/http/fleets.md) API can list existing fleets, their
configurations, and instances (if any):

<div class="termy">

```shell
$ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/fleets/list" \
    -X POST \
    -H "Authorization: Bearer &lt;user token&gt;" \
    -H 'Content-Type: application/json' \
    -d '{"include_imported": true}'
```

</div>

??? info "Offers"
    To check available offers via the HTTP API, call
    [`/runs/get_plan`](../reference/http/runs.md) with the same lightweight
    task specification used by `dstack offer`:

    <div class="termy">

    ```shell
    $ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/runs/get_plan" \
        -X POST \
        -H "Authorization: Bearer &lt;user token&gt;" \
        -H 'Content-Type: application/json' \
        -d '{
          "run_spec": {
            "configuration": {
              "type": "task",
              "commands": [":"],
              "image": "scratch",
              "user": "root",
              "resources": {
                "gpu": 0
              }
            }
          },
          "max_offers": 5
        }'
    ```

    </div>

    If `fleets` is not set in the run configuration, offers are returned from
    all configured backends. Use `"fleets": ["default"]` to restrict offers to
    a fleet.

    To group offers by GPU and other fields, use the
    [gpus](../reference/http/gpus.md) API.

Creating fleets uses `/fleets/get_plan` followed by `/fleets/apply`:

<div class="termy">

```shell
$ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/fleets/get_plan" \
    -X POST \
    -H "Authorization: Bearer &lt;user token&gt;" \
    -H 'Content-Type: application/json' \
    -d '{
      "spec": {
        "configuration": {
          "type": "fleet",
          "name": "cpu-fleet",
          "nodes": "0..1",
          "idle_duration": "1h",
          "resources": {
            "gpu": 0
          }
        },
        "profile": {}
      }
    }'
```

</div>

Then apply the fleet plan:

<div class="termy">

```shell
$ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/fleets/apply" \
    -X POST \
    -H "Authorization: Bearer &lt;user token&gt;" \
    -H 'Content-Type: application/json' \
    -d '{
      "plan": {
        "spec": {
          "configuration": {
            "type": "fleet",
            "name": "cpu-fleet",
            "nodes": "0..1",
            "idle_duration": "1h",
            "resources": {
              "gpu": 0
            }
          },
          "profile": {}
        }
      },
      "force": false
    }'
```

</div>

### Submit runs

Use the [runs](../reference/http/runs.md) API to submit
[dev environments](../concepts/dev-environments.md), [tasks](../concepts/tasks.md),
and [services](../concepts/services.md). The example below submits a task:

<div class="termy">

```shell
$ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/runs/apply" \
    -X POST \
    -H "Authorization: Bearer &lt;user token&gt;" \
    -H 'Content-Type: application/json' \
    -d '{
      "plan": {
        "run_spec": {
          "run_name": "hello-api",
          "configuration": {
            "type": "task",
            "commands": ["echo hello world"]
          }
        }
      },
      "force": false
    }'
```

</div>

Set `run_name` if a stable run name is needed. Otherwise, the server can
generate a run name.

Poll `/runs/get` to check the run status:

<div class="termy">

```shell
$ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/runs/get" \
    -X POST \
    -H "Authorization: Bearer &lt;user token&gt;" \
    -H 'Content-Type: application/json' \
    -d '{"run_name": "hello-api"}'
```

</div>

### Poll logs

Use the [logs](../reference/http/logs.md) API to poll logs. Get
`job_submission_id` from `/runs/get`, e.g. from `latest_job_submission.id`.

<div class="termy">

```shell
$ curl "&lt;server URL&gt;/api/project/&lt;project name&gt;/logs/poll" \
    -X POST \
    -H "Authorization: Bearer &lt;user token&gt;" \
    -H 'Content-Type: application/json' \
    -d '{
      "run_name": "hello-api",
      "job_submission_id": "&lt;job submission id&gt;",
      "limit": 100
    }'
```

</div>

Use `next_token` from the response to continue polling.

## Reference

For complete details on specific CLI commands and HTTP APIs, see the
[`dstack server`](../reference/cli/dstack/server.md) and
[server](../reference/http/server.md) references.

!!! info "OpenAPI"
    For complete information on the HTTP API, or to generate native clients,
    refer to [openapi.json](../reference/http/openapi.json).

!!! info "What's next?"
    1. Follow the [installation guide](../installation.md)
    2. Read about [projects](../concepts/projects.md)
    3. Check [fleets](../concepts/fleets.md),
       [dev environments](../concepts/dev-environments.md),
       [tasks](../concepts/tasks.md), and [services](../concepts/services.md)
