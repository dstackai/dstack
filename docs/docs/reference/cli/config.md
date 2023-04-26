# dstack config

This command allows you to configure a Hub project as a remote, enabling you to run workflows remotely.

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

## Arguments reference

The following arguments are required:

-  `--url URL` – (Required) The URL of the Hub application, e.g. `http://127.0.0.0.1`
-  `--project PROJECT` – (Required) The name of the project to use as a remote
- `--token TOKEN` – (Required) The personal access token of the Hub user