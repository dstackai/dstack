`dstack` is an open-source engine that automates infrastructure provisioning on any cloud — for development, training, and deployment of AI models.

## Configure backends

To let `dstack` run workloads in your cloud account(s), you need to configure cloud credentials 
in `~/.dstack/server/config.yml` under the `backends` property of the respective project.

Example:

```yaml
projects:
- name: main
  backends:
  - type: aws
    creds:
      type: access_key
      access_key: AIZKISCVKUKO5AAKLAEH
      secret_key: QSbmpqJIUBn1V5U3pyM9S6lwwiu8/fOJ2dgfwFdW
```

For further backend configuration details, refer to [Installation](https://dstack.ai/docs/installation/).

## Start the server

Starting the `dstack` server via Docker can be done the following way:

```shell
docker run -p 3000:3000 -v $HOME/.dstack/server/:/root/.dstack/server dstackai/dstack

The dstack server is running at http://0.0.0.0:3000
The admin user token is 'bbae0f28-d3dd-4820-bf61-8f4bb40815da'
```

## Set up the CLI

The client is configured via `~/.dstack/config.yml` with the server address, user token, and
the project name.

To configure this, use the `dstack config` command:

```shell
dstack config --project main --server http://0.0.0.0:3000 --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
```

This will update `~/.dstack/config` allowing the CLI and API to connect to the server by default.

## Environment variables

Here's the list of environment variables which you can override:

- `DSTACK_SERVER_DIR` – (Optional) The path to the directory where the `dstack` server stores the state. Defaults to `/root/.dstack/server`.
- `DSTACK_SERVER_ADMIN_TOKEN` – (Optional) The default token of the `admin` user. By default, it's generated randomly
  at the first startup.

## Persist state

`dstack` stores its state in the `$DSTACK_SERVER_DIR/data` folder (by default ``/root/.dstack/server/data`) using
SQLite.

### Use Litestream to replicate state 

`dstack` can automatically replicate its state to cloud object storage via Litestream by configuring the necessary
environment variables.

- `LITESTREAM_REPLICA_URL` - The url of the cloud object storage.
  Examples: `s3://<bucket-name>/<path>`, `gcs://<bucket-name>/<path>`, `abs://<storage-account>@<container-name>/<path>`, etc.

#### AWS S3

To persist state into an AWS S3 bucket, provide the following environment variables:

- `AWS_ACCESS_KEY_ID` - The AWS access key ID
- `AWS_SECRET_ACCESS_KEY` -  The AWS secret access key

#### GCP Storage

To persist state into an AWS S3 bucket, provide one of the following environment variables:

- `GOOGLE_APPLICATION_CREDENTIALS` - The path to the GCP service account key JSON file
- `GOOGLE_APPLICATION_CREDENTIALS_JSON` - The GCP service account key JSON

#### Azure Blob Storage

To persist state into an Azure blog storage, provide the following environment variable.

- `LITESTREAM_AZURE_ACCOUNT_KEY` - The Azure storage account key

More [details](https://litestream.io/guides/) on options for configuring replication.

_**️Note:** The use of Litestream requires that only one instance of the dstack server is running at a time._

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs/)
* [Examples](https://github.com/dstackai/dstack/blob/master/examples/README.md)
* [Changelog](https://dstack.ai/changelog)
* [Discord](https://discord.gg/u8SmfwPpMd)
 
##  Licence

[Mozilla Public License 2.0](https://github.com/dstackai/dstack/blob/master/LICENSE.md)