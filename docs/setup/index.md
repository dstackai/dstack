## Install the CLI

Use `pip` to install `dstack`:

<div class="termy">

```shell
$ pip install dstack
```

</div>

!!! info "NOTE:"
    To run workflows locally, it is required to have either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    pre-installed.

## Configure a remote

By default, workflows run locally. To run workflows remotely (e.g. in a configured cloud account),
configure a remote using the `dstack config` command.

<div class="termy">

```shell
$ dstack config
? Choose backend. Use arrows to move, type to filter
> [aws]
  [gcp]
  [hub]
```

</div>

Choose `hub` if you prefer managing cloud credentials and settings through a user interface while working in a team. 

For running remote workflows with local cloud credentials, select `aws` or `gcp`.

Check [AWS](aws.md), [GCP](gcp.md), or [Hub](hub.md) for details.