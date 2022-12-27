# CLI

Below is the list of support CLI commands.

## dstack run

This command runs a workflow defined in the current Git repo. 

The command provisions the required compute resources (in a configured cloud), fetches the same version of code 
(as you have locally), downloads the deps, and runs the workflow, saves artifacts, and tears down compute resources.

[//]: # (!!! info "NOTE:")
[//]: # (    Make sure to use the CLI from within a Git repo directory.)
[//]: # (    When you run a workflow, dstack detects the current branch, commit hash, and local changes.)

### Usage

```shell
dstack run [-h] WORKFLOW [-d] [-r] [-t TAG] [OPTIONS ...] [ARGS ...]
```

#### Arguments reference

The following arguments are required:

- `WORKFLOW` - (Required) A name of a workflow defined in 
   one of the YAML files in `./dstack/workflows`.

The following arguments are optional:

- `-t TAG`, `--tag TAG` - (Optional) A tag name. Warning, if the tag exists, it will be overridden.
- `-r`, `--remote`, - (Optional) Run the workflow in the cloud.
  or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) to be installed locally.
-  `-d`, `--detach` - (Optional) Run the workflow in the detached mode. Means, the `run` command doesn't
  poll for logs and workflow status, but exits immediately. 
- `OPTIONS` – (Optional) Use `OPTIONS` to override workflow parameters defined in the workflow YAML file
- `ARGS` – (Optional) Use `ARGS` to [pass arguments](../../examples/index.md#args) to the workflow
  (can be accessed via `${{ run.args }}` from the workflow YAML file).
-  `-h`, `--help` - (Optional) Shows help for the `dstack run` command. Combine it with the name of the workflow
   to see how to override workflow parameters defined in the workflow YAML file

!!! info "NOTE:"
    By default, it runs it in the attached mode, so you'll see the output in real-time as your 
    workflow is running.

## dstack ps

This command shows status of runs within the current Git repo.

### Usage

```shell
dstack ps [-a | RUN]
```

#### Arguments reference

The following arguments are optional and mutually exclusive:

-  `-a`, `--all` – (Optional) Show status of all runs
- `RUN` - (Optional) A name of a run

!!! info "NOTE:"
    If `-a` is not used, the command shows only the status of active runs, the last finished one.

## dstack push

The `push` command pushes the artifacts of a local run to the configured remote (e.g. 
to the configured cloud account).

### Usage

```shell
dstack push RUN
```

### Arguments reference

The following arguments are required:

- `RUN` - A name of a run

## dstack pull

The `pull` command downloads the artifacts of a given run or tag from the configured remote (e.g. 
to the configured cloud account) to the local cache (`~/.dstack/artifacts`).

### Usage

```shell
dstack pull (RUN | :TAG)
```

### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `:TAG` - A name of a tag

## dstack stop

This command stops run(s) within the current Git repo.

### Usage

```shell
dstack stop [-x] [-y] (RUN | -a)
```

#### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a particular run
-  `-a`, `--all` – Stop all unfinished runs 

The following arguments are optional:

-  `-x`, `--abort` – (Optional) Don't wait for a graceful stop and abort the run immediately 
-  `-y`, `--yes` – (Optional) Don't ask for confirmation 

## dstack logs

This command shows the output of a given run within the current Git repo.

### Usage

```shell
dstack logs [-a] [-s SINCE] RUN
```

#### Arguments reference

The following arguments are required:

- `RUN` - (Required) A name of a run

The following arguments are optional:

-  `-a`, `--attach` – (Optional) Whether to continuously poll for new logs while the workflow is still running. 
   By default, the command will exit once there are no more logs to display. To exit from this mode, use `Ctrl+C`.
- `-s SINCE`, `--since SINCE` – (Optional) From what time to begin displaying logs. By default, logs will be displayed
  starting from 24 hours in the past. The value provided can be an ISO 8601 timestamp or a
  relative time. For example, a value of `5m` would indicate to display logs starting five
  minutes in the past.

## dstack ls

The `ls` command lists the files of the artifacts of a given run or tag.

### Usage

```shell
dstack ls (RUN | :TAG)
```

### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a run
- `:TAG` - A name of a tag

## dstack tags list

The `tags list` command lists tags.

### Usage

```shell
dstack tags list
```

## dstack tags add

The `tags add` command creates a new tag. A tag and its artifacts can be later added as a dependency in a workflow.

There are two ways of creating a tag:

1. Tag a finished run 
2. Upload local data

### Usage

```shell
dstack tags add TAG (-r RUN | -a PATH ...)
```

### Arguments reference

The following argument is required:

- `TAG` – (Required) A name of the tag. Must be unique within the current Git repo.

One of the following arguments is also required:

- `-r`, `--run` - A name of a run
- `-a PATH`, `--artifact PATH` - A path to a local folder to be uploaded as an artifact.

### Examples:

Tag the finished run `wet-mangust-1` with the `some_tag_1` tag:

```shell
dstack tags add some_tag_1 wet-mangust-1
```

Uploading two local folders `./output1` and `./output2` to create the `some_tag_2` tag:

```shell
dstack tags add some_tag_2 -a ./output1 -a ./output2
```

!!! info "NOTE:"
    To list or download the artifacts of a tag, use the `dstack artifacts list :TAG` and 
    `dstack artifacts download :TAG` commands.

## dstack tags delete

### Usage

```shell
dstack tags delete [-y] TAG
```

#### Arguments reference

The following arguments are required:

- `TAG` - (Required) A name of a tag

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 

## dstack init

This command authorizes dstack to use the current Git credentials (to fetch your code when running workflows).
Not needed for public repos.

### Usage

```shell
dstack init [-t OAUTH_TOKEN | -i SSH_PRIVATE_KEY]
```

!!! info "NOTE:"
    The credentials are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager).

#### Arguments reference

The following arguments are optional:

- `-t OAUTH_TOKEN`, `--token OAUTH_TOKEN` - (Optional) An authentication token for GitHub
- `-i SSH_PRIVATE_KEY`, `--identity SSH_PRIVATE_KEY` – A path to the private SSH key file 

!!! info "NOTE:"
    If no arguments are provided, `dstack` uses the credentials configured in
    `~/.config/gh/hosts.yml` or `./.ssh/config` for the current Git repo.

## dstack config

This command configures the AWS region and S3 bucket, where dstack will provision compute resources and save data.

### Usage

```shell
dstack config
```

Make sure to use an S3 bucket name that isn't used by other AWS accounts.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

The configuration is stored in `~/.dstack/config.yaml`.

## dstack secrets list

The `secrets list` command lists the names of global secrets.

### Usage

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

## dstack rm

Use this command to remove finished runs within the current Git repo.

### Usage

```shell
dstack rm [-y] (RUN | -a)
```

#### Arguments reference

One of the following arguments is required:

- `RUN` - A name of a particular run
-  `-a`, `--all` – Remove all finished runs 

The following arguments are optional:

-  `-y`, `--yes` – (Optional) Don't ask for confirmation 
