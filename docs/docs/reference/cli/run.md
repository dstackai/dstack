# dstack run

This command runs a given configuration.

## Usage

<div class="termy">

```shell
$ dstack run --help
Usage: dstack run [--project PROJECT] [--profile PROFILE] [-d] [--reload] WORKING_DIR [ARGS ...]

Positional Arguments:
  WORKING_DIR          The working directory of the run
  ARGS                 Run arguments

Options:
  --f FILE             The path to the run configuration file. Defaults to WORKING_DIR/.dstack.yml.
  --project PROJECT    The name of the project
  --profile PROFILE    The name of the profile
  -d, --detach         Do not poll logs and run status
  --reload             Enable auto-reload
  -t, --tag TAG        A tag name. Warning, if the tag exists, it will be overridden.
```

</div>

[//]: # (TODO: Ports aren't part of the `dstack run --help` output)

## Arguments reference

The following arguments are required:

- `WORKING_DIR` - (Required) The working directory of the run (e.g. `.`)

The following arguments are optional:

- `-f FILE`, `--f FILE` – (Optional) The path to the run configuration file. Defaults to `WORKING_DIR/.dstack.yml`.
- `--project PROJECT` – (Optional) The name of the project
- `--project PROJECT` – (Optional) The name of the profile
- `--reload` – (Optional) Enable auto-reload 
- `-d`, `--detach` – (Optional) Run in the detached mode. Means, the command doesn't
  poll logs and run status.
- `-p PORT [PORT ...]`, `--port PORT [PORT ...]` – (Optional) Requests ports or define mappings for them (`APP_PORT:LOCAL_PORT`)
- `-t TAG`, `--tag TAG` – (Optional) A tag name. Warning, if the tag exists, it will be overridden.
- `ARGS` – (Optional) Use `ARGS` to pass custom run arguments

[//]: # (Tags should be dropped)

!!! info "NOTE:"
    By default, it runs it in the attached mode, so you'll see the output in real-time.