# Install the CLI

Use `pip` to install `dstack`:

<div class="termy">

```shell
$ pip install dstack --upgrade
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
```

</div>

[//]: # (If you intend to collaborate in a team and would like to manage cloud credentials, users and other settings )
[//]: # (via a user interface, it is recommended to choose `hub`.)

[//]: # (!!! info "NOTE:")
[//]: # (    Choosing the `hub` remote with the `dstack config` CLI command requires you to have a Hub application up)
[//]: # (    and running. Refer to [Hub]&#40;#hub&#41; for the details.)

[//]: # (If you intend to work alone and wish to run workflows directly in the cloud without any intermediate, )
[//]: # (feel free to choose `aws` or `gcp`.)

If you intend to run remote workflows directly in the cloud using local cloud credentials, 
feel free to choose `aws` or `gcp`.

[//]: # (If you would like to manage cloud credentials, users and other settings centrally)
[//]: # (via a user interface, it is recommended to choose `hub`. )

<div class="grid cards" markdown>
- [**AWS** 
   Run workflows directly in an AWS account using local credentials.
  ](aws.md)
- [**GCP**
   Run workflows directly in an GCP account using local credentials.
  ](gcp.md)
</div>