# dstack secrets

## dstack secrets list

The `secrets list` command lists the names of global secrets.

### Usage

<div class="termy">

```shell
$ dstack secrets list
```

</div>

## dstack secrets add

Secrets allow to use sensitive data within workflows (such as passwords or security tokens) without 
hard-coding them inside the code.

Secrets are passed to running workflows via environment variables.

The `secrets add` command adds a new secret.

!!! info "NOTE:"
    Secret are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

### Usage

```shell
$ dstack secrets add --help
Usage: dstack secrets add [-h] [-y] NAME [VALUE]

Positional Arguments:
  NAME        The name of the secret
  VALUE       The value of the secret

Optional Arguments:
  -y, --yes   Don't ask for confirmation
```

### Arguments reference

The following arguments are required:

- `NAME` – (Required) A name of the secret. Must be unique within the current Git repo.

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
- `VALUE` – (Optional) The value of the secret. If not specified, dstack prompts the user to enter it via a masked input.


## dstack secrets delete

### Usage

<div class="termy">

```shell
$ dstack secrets delete --help
usage: dstack secrets delete [-h] NAME

positional arguments:
  NAME        The name of the secret
```

</div>

### Arguments reference

The following arguments are required:

- `NAME` - (Required) A name of a secret

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 