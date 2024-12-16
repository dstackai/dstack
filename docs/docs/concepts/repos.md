# Repos

Running a dev environment, task, or service with [`dstack apply`](../reference/cli/index.md#dstack-apply) in a directory
mounts the contents of that directory to the container’s `/workflow` directory and sets it as the container’s current working directory.
This allows the configuration to access the files from the directory.

## Initialize a repo

Before using [`dstack apply`](../reference/cli/index.md#dstack-apply) in a directory, initialize that directory first as a repo by running [`dstack init`](../reference/cli/index.md#dstack-init).
The repo can be either a normal directory or a cloned Git repo.

[`dstack init`](../reference/cli/index.md#dstack-init) is not required if you pass `-P` (or `--repo`) to [`dstack apply`](../reference/cli/index.md#dstack-apply) (see below).

### Git credentials

If the directory is a cloned Git repo, [`dstack init`](../reference/cli/index.md#dstack-init) grants the `dstack` server access by uploading the current user's default
Git credentials, ensuring that dstack can clone the Git repo when running the container.

To use custom credentials, pass them directly with `--token` (GitHub token) or `--git-identity` (path to a private SSH
key).

> The `dstack` server stores Git credentials individually for each `dstack` user and encrypts them if encryption is
> enabled.

### .gitignore and folder size

If the directory is cloned Git repo, [`dstack apply`](../reference/cli/index.md#dstack-apply) uploads to the `dstack` server only local changes.
If the directory is not a cloned Git repo, it uploads the entire directory.

Uploads are limited to 2MB. Use `.gitignore` to exclude unnecessary files from being uploaded.

### Initialize as a regular directory

If the directory is a cloned Git repo but you want to initialize it as a regular directory, use
`--local` with [`dstack init`](../reference/cli/index.md#dstack-init).

## Override the repo

You can customize the default repo settings in several ways.

### Pass the repo path

By default, [`dstack apply`](../reference/cli/index.md#dstack-apply) uses the current folder as the repo.

To specify a different folder, pass its path using `-P` (or `--repo`):

<div class="termy">

```shell    
$ dstack apply -f .dstack.yml -P ../parent_dir 
```

</div>

### Pass a remote Git repo URL

Run a configuration directly from a remote Git repo without cloning it locally by passing the repo URL with `-P` (or
`--repo`):

<div class="termy">

```shell
$ dstack apply -f .dstack.yml -P https://github.com/dstackai/dstack.git
```

</div>

### Automatic initialization

When overriding the repo with `-P` (or `--repo`), pass Git credentials directly using `--token` or `--git-identity` to skip
[`dstack init`](../reference/cli/index.md#dstack-init).

### Do not use a repo

To run a configuration without a repo (the `/workflow` directory inside the container will be empty), use `--no-repo`:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml --no-repo
```

</div>

## What's next?

1. Read about [dev environments](../dev-environments.md), [tasks](../tasks.md), [services](../services.md)