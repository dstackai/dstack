# Repos

Running [`dstack apply`](../reference/cli/index.md#dstack-apply) in a folder uploads its contents and mounts them to the container’s `/workflow` directory. 
This makes files from the folder accessible within the configuration.

## Initialize a repo

Before using [`dstack apply`](../reference/cli/index.md#dstack-apply), initialize the folder as a repo by running [`dstack init`](../reference/cli/index.md#dstack-init) once. 
The folder can be either a local directory or a remote Git repo.

### Git credentials

If the folder is a remote Git repo, [`dstack init`](../reference/cli/index.md#dstack-init) grants the `dstack` server access by uploading the current user's default
Git credentials. This ensures the server can fetch the repo’s contents when needed.

To use custom credentials, pass them directly with `--token` (GitHub token) or `--git-identity` (path to a private SSH
key).

> The `dstack` server stores Git credentials individually for each `dstack` user and encrypts them if encryption is
> enabled.

### .gitignore and folder size

For remote Git repos, [`dstack apply`](../reference/cli/index.md#dstack-apply) uploads only local changes. For local folders, it uploads the entire directory.

Uploads are limited to 2MB. Use `.gitignore` to exclude unnecessary files from being uploaded.

> To initialize a remote Git repo as a regular folder, use `--local` with [`dstack init`](../reference/cli/index.md#dstack-init).

### Override the repo

You can customize the default repo settings in several ways.

### Pass the repo path

By default, [`dstack apply`](../reference/cli/index.md#dstack-apply) uses the current folder as the repo.

To specify a different folder, pass its path using `-P` (or `--repo`):

<div class="termy">

```shell    
$ dstack apply -f .dstack.yml -P ../parent_dir 
```

</div>

### Pass a remote repo URL

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

To run a configuration without any repo, use `--no-repo`:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml --no-repo
```

</div>

## What's next?

1. Read about [dev environments](../dev-environments.md), [tasks](../tasks.md), [services](../services.md)