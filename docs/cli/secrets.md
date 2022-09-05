# secrets

The `secrets` command manages global secrets.

Secrets allow to use sensitive data within workflows (such as passwords or security tokens) without 
hard-coding them inside the code.

A secret has a name and a value. All secrets are passed to the running workflows via environment variables.

Secret values are stored in the cloud storage of credentials within the configured backend 
(for AWS, it's Secrets Manager).

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
dstack secrets add [-o] [-y] NAME VALUE
```

### Arguments reference

The following arguments are required:

- `NAME` – (Required) A name of the secret. Must be unique within the current Git repository.
- `VALUE` – (Required) The value of the secret.
- 
The following arguments are optional:

-  `-o`, `--override` – (Optional) Override the secret if it exists 
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 


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
