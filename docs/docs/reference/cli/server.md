# dstack start

This command starts the Hub server. The Hub is required to run workflows.

## Usage

<div class="termy">

```shell
$ dstack server --help
#GENERATE#
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