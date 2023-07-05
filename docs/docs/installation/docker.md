# Docker

!!! info "NOTE:"
    As an alternative to the [`dstack start`](../reference/cli/start.md) command, you can run the `dstack` server via
    Docker. This is recommended if you want to deploy the server in an environment that supports Docker.

Here's how to run `dstack` via Docker:

<div class="termy">

```shell
$ docker run --name dstack -p &lt;port-on-host&gt;:3000 \ 
  -v &ltpath-to-data-directory&gt;:/root/.dstack/hub \
  dstackai/dstack
```

</div>

## Environment variables

Here's the list of environment variables which you can override:

- `DSTACK_HUB_ADMIN_TOKEN` – (Optional) The default token of the `admin` user. By default, it's generated randomly
  at the first startup.
- `DSTACK_HUB_DATA` – (Optional) The path to the directory where the Hub server stores the state. Defaults to `~/.dstack/hub/data`.

### Persisting state

By default, `dstack` saves state in a local directory (see `DSTACK_HUB_DATA`).
If you want to persist state automatically to a cloud object storage, you can configure the following environment
variables.

- `LITESTREAM_REPLICA_URL` - The url of the cloud object storage.
  Examples: `s3://<bucket-name>/<path>`, `gcs://<bucket-name>/<path>`, `abs://<storage-account>@<container-name>/<path>`, etc.

??? info "AWS S3"
    To persist state into an AWS S3 bucket, provide the following environment variables:

    - `AWS_ACCESS_KEY_ID` - The AWS access key ID
    - `AWS_SECRET_ACCESS_KEY` -  The AWS secret access key

??? info "GCP Storage"
    To persist state into an AWS S3 bucket, provide one of the following environment variables:

    - `GOOGLE_APPLICATION_CREDENTIALS` - The path to the GCP service account key JSON file
    - `GOOGLE_APPLICATION_CREDENTIALS_JSON` - The GCP service account key JSON

??? info "Azure Blob Storage"
    To persist state into an Azure blog storage, provide the following environment variable.

    - `LITESTREAM_AZURE_ACCOUNT_KEY` - The Azure storage account key

More [details](https://litestream.io/guides/) on options for configuring persistent state.

## Limitation

When you run `dstack` via Docker, it doesn't allow you to configure a project that runs dev environments, pipelines, and apps locally.
You can only configure the projects that run dev environments, pipelines, and apps in the cloud. 

!!! info "NOTE:"
    If you want `dstack` to run dev environments,
    pipelines, and apps both locally and in the cloud, it is recommended to start the server using the `dstack start` command.