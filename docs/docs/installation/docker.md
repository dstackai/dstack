# Docker

Here's how to run the `dstack` server via Docker:

<div class="termy">

```shell
$ docker run --name dstack -p &lt;port-on-host&gt;:3000 \ 
  -v ~/dstack/server:/root/.dstack/server \
  dstackai/dstack
```

</div>

!!! info "NOTE:"
    If you run the `dstack` server via Docker, it will not allow you to run workloads locally. 
    To run workloads locally, make sure to use [`pip`](pip.md).

    Running the `dstack` server via Docker makes sense only if you intend to deploy the `dstack` server 
    outside of your machine to run workloads in the cloud.

## Environment variables

Here's the list of environment variables which you can override:

- `DSTACK_SERVER_ADMIN_TOKEN` – (Optional) The default token of the `admin` user. By default, it's generated randomly
  at the first startup.
- `DSTACK_SERVER_DATA` – (Optional) The path to the directory where the `dstack`server stores the state. Defaults to `~/.dstack/server`.

??? info "Persisting state in a cloud storage"

    By default, `dstack` saves state in a local directory (see `DSTACK_SERVER_DATA`).
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