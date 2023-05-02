# dstack config

This command configures a Hub project.

The configuration is stored in `~/.dstack/config.yaml`.

## Usage

<div class="termy">

```shell
$ dstack config hub --help
Usage: dstack config hub [-h] --url URL --project PROJECT --token TOKEN

Options:
  --url URL           The URL of the Hub application, e.g. http://127.0.0.0.1
  --project PROJECT   The name of the project to use as a remote
  --token TOKEN       The personal access token of the Hub user
```

</div>

!!! info "NOTE:"
    You can configure multiple projects and use them interchangeably (by passing the `--project` argument to the `dstack 
    run` command. Any project can be set as the default by passing `--default` to the `dstack config` command.

    Configuring multiple projects can be convenient if you want to run workflows both locally and in the cloud or if 
    you would like to use multiple clouds.

## Arguments reference

The following arguments are required:

-  `--url URL` – (Required) The URL of the Hub application, e.g. `http://127.0.0.0.1`
-  `--project PROJECT` – (Required) The name of the project to use as a remote
- `--token TOKEN` – (Required) The personal access token of the Hub user