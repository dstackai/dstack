# dstack secrets

Secrets allow to use sensitive data within workflows (such as passwords or security tokens) without 
hard-coding them inside the code.
Secrets are passed to running workflows via environment variables.

!!! info "NOTE:"
    If the project is configured to use the cloud, secrets are stored in the encrypted cloud storage.

## dstack secrets list

The `dstack secrets list` command displays the names of the secrets configured in the current repository.

### Usage

<div class="termy">

```shell
$ dstack secrets list
```

</div>

## dstack secrets add

The `dstack secrets add` command adds a new secret for the current repository.

### Usage

<div class="termy">

```shell
$ dstack secrets add --help
Usage: dstack secrets add [-h] [--project PROJECT] [-y] NAME [VALUE]

Positional Arguments:
  NAME               The name of the secret
  VALUE              The value of the secret

Optional Arguments:
  --project PROJECT  The name of the project to execute the command for
  -y, --yes          Don't ask for confirmation
```

</div>

### Arguments reference

The following arguments are required:

- `NAME` – (Required) A name of the secret. Must be unique within the current repository.

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the project to execute the command for
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
- `VALUE` – (Optional) The value of the secret. If not specified, dstack prompts the user to enter it via a masked input.


## dstack secrets delete

The `dstack secrets delete` command adds a new secret for the current repository.

### Usage

<div class="termy">

```shell    
$ dstack secrets delete --help
usage: dstack secrets delete [-h] [--project PROJECT] [-y] NAME

Positional Arguments:
  NAME               The name of the secret

Optional Arguments:
  --project PROJECT  The name of the project to execute the command for
  -y, --yes          Don't ask for confirmation
```

</div>

### Arguments reference

The following arguments are required:

- `NAME` - (Required) A name of a secret

The following arguments are optional:

- `--project PROJECT` - (Optional) The name of the project to execute the command for
- `-y`, `--yes` – (Optional) Don't ask for confirmation 