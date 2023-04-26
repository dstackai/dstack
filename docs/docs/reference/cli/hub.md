# dstack hub

This command starts the Hub application. Hub is required for running workflows remotely (e.g. in a configured cloud).

## Usage

<div class="termy">

```shell
$ dstack hub start --help
Usage: dstack hub start [-h] [--host HOST] [-p PORT] [-l LOG-LEVEL] [--token TOKEN]

Options:
  --host HOST           Bind socket to this host. Defaults to 127.0.0.1
  -p, --port PORT       Bind socket to this port. Defaults to 3000.
  --token TOKEN         The personal access token of the admin user. Is generated randomly by default.
```

</div>

## Arguments reference

The following arguments are optional:

-  `--host HOST` – (Optional) Bind socket to this host. Defaults to `127.0.0.1`
-  `-p PORT`, `--port PORT` – (Optional) Bind socket to this port. Defaults to `3000`.
-  `--token TOKEN` – (Optional) The personal access token of the admin user. Is generated randomly by default.