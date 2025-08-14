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

By default, `dstack` uses its own SSH key to attach to runs (`~/.dstack/ssh/id_rsa`).
It is possible to override this key via the `--ssh-identity` argument.

[//]: # (TODO: Provide examples)
