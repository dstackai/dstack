# dstack build

This command creates a build for a given configuration.

## Usage

<div class="termy">

```shell
$ dstack build --help
Usage: dstack build [--project PROJECT] [--profile PROFILE] [-d] [--reload] WORKING_DIR [ARGS ...]

Positional Arguments:
  WORKING_DIR          The working directory of the run
  ARGS                 Run arguments

Options:
  --f FILE             The path to the run configuration file. Defaults to WORKING_DIR/.dstack.yml.
  --project PROJECT    The name of the project
  --profile PROFILE    The name of the profile
```

</div>

## Arguments reference

The following arguments are required:

- `WORKING_DIR` - (Required) The working directory of the run (e.g. `.`)

The following arguments are optional:

- `-f FILE`, `--f FILE` – (Optional) The path to the run configuration file. Defaults to `WORKING_DIR/.dstack.yml`.
- `--project PROJECT` – (Optional) The name of the project
- `--profile PROFILE` – (Optional) The name of the profile
- `ARGS` – (Optional) Use `ARGS` to pass custom run arguments
