---
title: connect
description: Connect directly to a running dev environment through the SSH proxy
---

# dstack connect

This command connects directly to a running dev environment through the
server's configured SSH proxy. It can open an interactive SSH session or the
IDE configured by the dev environment without keeping `dstack attach` running.

## Usage

<div class="termy">

```shell
$ dstack connect --help
#GENERATE#
```

</div>

Interactive SSH is the default mode:

```shell
dstack connect &lt;run name&gt;
```

Use `--ide` to open the IDE selected by the dev environment configuration:

```shell
dstack connect --ide &lt;run name&gt;
```

The supported IDEs are VS Code, Cursor, Windsurf, and Zed. You can request one
explicitly with `--vscode`, `--cursor`, `--windsurf`, or `--zed`. An explicit
option fails if it does not match the run configuration. On Linux, the Zed
launcher can be named either `zed` or `zeditor`.

Use `--replica` and `--job` to select a job. Without `--replica`, the command
uses any running replica with the selected job number.

## Pin the SSH proxy

Automation can require an exact proxy endpoint:

```shell
dstack connect --expect-sshproxy proxy.example.com:2222 &lt;run name&gt;
```

The port defaults to `22`. Bracket IPv6 addresses, for example
`[2001:db8::1]:2222`. If the run reports a different endpoint, the command
fails before downloading a key, updating local SSH configuration, or launching
a client.

## Requirements and behavior

`dstack connect` is intentionally limited to a running dev environment owned by
the current user. The server must have the SSH proxy enabled and provide a
complete, internally consistent SSH and IDE connection record for the selected
job. The command never falls back to direct host SSH.

The CLI validates the proxy host, port, upstream identifier, SSH command, IDE
URL, and remote working directory before changing local state. It then stores a
local `dstack-direct-*` alias in `~/.dstack/ssh/config` using the current user's
built-in SSH key. The selected job's dynamic proxy identifier stays in the
`user@alias` target, so resolving the connection again after a retry does not
reuse a stale proxy session.

Client processes are launched with argument vectors, without a shell. Remote
paths in IDE URLs are percent-encoded before they are passed to the local IDE.

This command does not forward ports or stream logs. Use
[`dstack attach`](attach.md) when those attached-session features are required.

## Python API

Use `Run.get_direct_connection()` to perform the same refresh, validation, key
setup, and SSH alias update without launching a client:

```python
import subprocess

from dstack.api import Client

client = Client.from_config()
run = client.runs.get("my-dev-environment")
if run is None:
    raise RuntimeError("Run not found")

connection = run.get_direct_connection()
subprocess.run(connection.ssh_command, check=True)
```

`RunDirectConnection.ssh_command` and `ide_command` are argument tuples. Pass
them directly to a subprocess API; do not join them into a shell command.
