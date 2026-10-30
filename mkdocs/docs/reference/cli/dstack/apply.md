# dstack apply

This command applies a given configuration. If a resource does not exist, `dstack apply` creates the resource.
If a resource exists, `dstack apply` updates the resource in-place or re-creates the resource if the update is not possible.

To mount a Git repo to the run's container, specify it via [`repos`](../../../concepts/dev-environments.md#repos) in the configuration
or via `-P` (or `--repo`).

If a Git repo is private, `dstack` will automatically try to use your default Git credentials (from
`~/.ssh/config` or `~/.config/gh/hosts.yml`).
If you want to use custom credentials, you can provide them with `--token` or `--git-identity`, or with [`dstack init`](init.md).

## Usage

<div class="termy">

```shell
$ dstack apply --help
#GENERATE#
```

</div>

## User SSH key

By default, `dstack` attaches to runs using the user's SSH key automatically created and managed by `dstack`. The CLI downloads it from the server and stores it under `~/.dstack/ssh/`.
To use a different key for the run, pass the path to its private key via `--ssh-identity`.

!!! info "SSH proxy"
    If the [SSH proxy](../../../guides/server-deployment.md#ssh-proxy) is configured, you can also use any key uploaded under **SSH keys** in the user settings.

[//]: # (TODO: Provide examples)
