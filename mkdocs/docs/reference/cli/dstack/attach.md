# dstack attach

This command attaches to a given run. It establishes the SSH tunnel, forwards ports, and shows real-time run logs.

## Usage

<div class="termy">

```shell
$ dstack attach --help
#GENERATE#
```

</div>

## User SSH key

By default, `dstack` attaches to runs using the user's SSH key automatically created and managed by `dstack`. The CLI downloads it from the server and stores it under `~/.dstack/ssh/`.
To attach with a different key, pass the path to its private key via `--ssh-identity`.
If the run was submitted with `dstack apply --ssh-identity`, pass the same key.

!!! info "SSH proxy"
    If the [SSH proxy](../../../guides/server-deployment.md#ssh-proxy) is configured, you can also use any key uploaded under **SSH keys** in the user settings.

[//]: # (TODO: Provide examples)
