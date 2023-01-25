# dstack secrets

## dstack secrets list

The `secrets list` command lists the names of global secrets.

## Usage

```shell
dstack secrets list
```

## dstack secrets add

Secrets allow to use sensitive data within workflows (such as passwords or security tokens) without 
hard-coding them inside the code.

Secrets are passed to running workflows via environment variables.

The `secrets add` command adds a new secret.

!!! info "NOTE:"
    Secret are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

### Usage

```shell
dstack secrets add [-y] NAME [VALUE]
```

### Arguments reference

The following arguments are required:

- `NAME` – (Required) A name of the secret. Must be unique within the current Git repo.

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
- `VALUE` – (Optional) The value of the secret. If not specified, dstack prompts the user to enter it via a masked input.


## dstack secrets delete

### Usage

```shell
dstack secrets delete [-y] NAME
```

#### Arguments reference

The following arguments are required:

- `NAME` - (Required) A name of a secret

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 