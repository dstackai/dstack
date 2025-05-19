# dstack config

!!! info "Deprecated"
    The `dstack config` is deprecated. Use [`dstack project`](project.md) instead.

Both the CLI and API need to be configured with the server address, user token, and project name
via `~/.dstack/config.yml`.

At startup, the server automatically configures CLI and API with the server address, user token, and
the default project name (`main`). This configuration is stored via `~/.dstack/config.yml`.

To use CLI and API on different machines or projects, use the `dstack config` command.

## Usage

<div class="termy">

```shell
$ dstack config --help
#GENERATE#
```

</div>

[//]: # (TODO: Provide examples)
