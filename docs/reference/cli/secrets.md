# dstack secrets

This command manages global secrets.

Secrets allow to use sensitive data within workflows (such as passwords or security tokens) without 
hard-coding them inside the code.

Secrets are passed to running workflows via environment variables.

!!! info "NOTE:"
    Secret are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

The `secrets` command supports the following subcommands: `list`, `add`, and `delete`.

## secrets list

The `secrets list` command lists the names of global secrets.

### Usage

```shell
dstack secrets list
```

## secrets add

The `secrets add` command adds a new secret.

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


## secrets delete

### Usage

```shell
dstack secrets delete [-y] NAME
```

#### Arguments reference

The following arguments are required:

- `NAME` - (Required) A name of a secret

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
