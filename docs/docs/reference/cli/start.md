# dstack start

This command starts the Hub application. The Hub application is required to run workflows.

## Usage

<div class="termy">

```shell
$ dstack start --help
Usage: dstack start [-h] [--host HOST] [-p PORT] [-l LOG-LEVEL] [--token TOKEN]

Options:
  --host HOST           Bind socket to this host. Defaults to 127.0.0.1
  -p, --port PORT       Bind socket to this port. Defaults to 3000.
  --token TOKEN         The personal access token of the admin user. Is generated randomly by default.
```

</div>

!!! info "NOTE:"
    On the first run, this command creates the default project to run workflows locally and updates the local config 
    accordingly (`~/.dstack/config.yaml`).

## Arguments reference

The following arguments are optional:

-  `--host HOST` – (Optional) Bind socket to this host. Defaults to `127.0.0.1`
-  `-p PORT`, `--port PORT` – (Optional) Bind socket to this port. Defaults to `3000`.
-  `--token TOKEN` – (Optional) The personal access token of the admin user. Is generated randomly by default.