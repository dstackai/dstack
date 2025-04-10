# Repos

Running a dev environment, task, or service with [`dstack apply`](../reference/cli/dstack/apply.md) in a directory
mounts the contents of that directory to the container’s `/workflow` directory and sets it as the container’s current working directory.
This allows accessing the directory files from within the run.

## Initialize a repo

To use a directory with `dstack apply`, it must first be initialized as a repo by running [`dstack init`](../reference/cli/dstack/init.md).
The directory can be either a regular local directory or a cloned Git repo.

[`dstack init`](../reference/cli/dstack/init.md) is not required if you pass `-P` (or `--repo`) to [`dstack apply`](../reference/cli/dstack/apply.md) (see below).

### Git credentials

If the directory is a cloned Git repo, [`dstack init`](../reference/cli/dstack/init.md) grants the `dstack` server access by uploading the current user's default
Git credentials, ensuring that dstack can clone the Git repo when running the container.

To use custom credentials, pass them directly with `--token` (GitHub token) or `--git-identity` (path to a private SSH
key).

> The `dstack` server stores Git credentials individually for each `dstack` user and encrypts them if encryption is
> enabled.

### .gitignore and folder size

If the directory is cloned Git repo, [`dstack apply`](../reference/cli/dstack/apply.md) uploads to the `dstack` server only local changes.
If the directory is not a cloned Git repo, it uploads the entire directory.

Uploads are limited to 2MB. Use `.gitignore` to exclude unnecessary files from being uploaded.

### Initialize as a local directory

If the directory is a cloned Git repo but you want to initialize it as a regular local directory,
use `--local` with [`dstack init`](../reference/cli/dstack/init.md).

## Specify the repo

By default, `dstack apply` uses the current directory as a repo and requires `dstack init`.
You can change this by explicitly specifying the repo to use for `dstack apply`.

### Pass the repo path

To use a specific directory as the repo, specify its path using `-P` (or `--repo`):

<div class="termy">

```shell    
$ dstack apply -f .dstack.yml -P ../parent_dir 
```

</div>

### Pass a remote Git repo URL

To use a remote Git repo without cloning it locally, specify the repo URL with `-P` (or `--repo`):

<div class="termy">

```shell
$ dstack apply -f .dstack.yml -P https://github.com/dstackai/dstack.git
```

</div>

### Automatic initialization

When specifying the repo with `-P` (or `--repo`), the repo is initialized automatically and
`dstack init` is not required.
If you use a private Git repo, you can pass Git credentials to `dstack apply` using `--token` or `--git-identity`.

### Do not use a repo

To run a configuration without a repo (the `/workflow` directory inside the container will be empty), use `--no-repo`:

<div class="termy">

```shell
$ dstack apply -f .dstack.yml --no-repo
```

</div>

## Store the repo on a volume

You can use [Volumes](../concepts/volumes.md) to persist repo changes without pushing them to the Git remote.
Attach a volume to the repo directory (`/workflow`) or any of its subdirectories.
`dstack` will clone the repo to the volume on the first run.
On subsequent runs, `dstack` will use the repo contents from the volume instead of cloning the repo.

## What's next?

1. Read about [dev environments](../concepts/dev-environments.md), [tasks](../concepts/tasks.md), [services](../concepts/services.md)
