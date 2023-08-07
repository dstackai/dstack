# dstack run

This command runs a given configuration.

## Usage

<div class="termy">

```shell
$ dstack run --help
Usage: dstack run [-h] [-f FILE] [-n NAME] [-y] [-d] [--project PROJECT] [--profile PROFILE]
                  [--reload]
                  WORKING_DIR [ARGS ...]

Positional Arguments:
  WORKING_DIR           The working directory of the run
  ARGS                  Run arguments

Options:
  -h, --help            Show this help message and exit
  -f, --file FILE       The path to the run configuration file. Defaults to
                        WORKING_DIR/.dstack.yml.
  -n, --name NAME       The name of the run. If not specified, a random name is assigned.
  -y, --yes             Do not ask for plan confirmation
  -d, --detach          Do not poll logs and run status
  --reload              Enable auto-reload
  --project PROJECT     The name of the project
  --profile PROFILE     The name of the profile
```

</div>

[//]: # (TODO: Ports aren't part of the `dstack run --help` output)

## Arguments reference

The following arguments are required:

- `WORKING_DIR` - (Required) The working directory of the run (e.g. `.`)

The following arguments are optional:

- `-f FILE`, `--f FILE` – (Optional) The path to the run configuration file. Defaults to `WORKING_DIR/.dstack.yml`.
- `-n NAME`, `--name NAME` - (Optional) The name of the run. If not specified, a random name is assigned.
- `-y`, `--yes` - (Optional) Do not ask for plan confirmation
- `-d`, `--detach` – (Optional) Run in the detached mode to disable logs and run status polling. By default, the run is in the attached mode, so the logs are printed in real-time.
- `--reload` – (Optional) Enable auto-reload 
- `--project PROJECT` – (Optional) The name of the project
- `--profile PROJECT` – (Optional) The name of the profile

[//]: # (- `-t TAG`, `--tag TAG` – &#40;Optional&#41; A tag name. Warning, if the tag exists, it will be overridden.)
- `-p PORT`, `--port PORT` – (Optional) Requests port or define mapping (`LOCAL_PORT:CONTAINER_PORT`)
- `-e ENV`, `--env ENV` – (Optional) Set environment variable (`NAME=value`)
- `--gpu` – (Optional) Request a GPU for the run. Specify any: name, count, memory (`NAME:COUNT:MEMORY` or `NAME` or `COUNT:MEMORY`, etc...)
- `ARGS` – (Optional) Use `ARGS` to pass custom run arguments

Spot policy (the arguments are mutually exclusive):

- `--spot-policy` – The policy for provisioning spot or on-demand instances: `spot`, `on-demand`, or `auto`. 
- `--spot` – A shorthand for `--spot-policy spot`
- `--on-demand` – A shorthand for `--spot-policy on-demand`
- `--spot-auto` – A shorthand for `--spot-policy auto`

Retry policy (the arguments are mutually exclusive):

- `--no-retry` – Do not retry the run on failure
- `--retry` – Retry the run on failure. Use a default retry limit (1h). 
- `--retry-limit` – Retry the run on failure with a custom retry limit, e.g. 4h or 1d

Build policies:

[//]: # (- `--use-build` – Use the build if available, otherwise fail)
- `--build` – If the environment is not pre-built yet, pre-build it. If the environment is already pre-built, reuse it.
- `--force-build` – Force pre-building the environment, even if it has been pre-built before.

[//]: # (- `--build-only` — Just create the build and save it)

[//]: # (Tags should be dropped)

!!! info "NOTE:"
    By default, the run is in the attached mode, so you'll see the output in real-time.
