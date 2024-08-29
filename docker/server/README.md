`dstack` is an open-source container orchestration engine designed for running AI workloads across any cloud or data
center. It simplifies dev environments, running tasks on clusters, and deployment.

The supported cloud providers include AWS, GCP, Azure, OCI, Lambda, TensorDock, Vast.ai, RunPod, and CUDO.
You can also use `dstack` to run workloads on on-prem clusters.

`dstack` natively supports NVIDIA GPU, AMD GPU, and Google Cloud TPU accelerator chips.

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
dstack config --project main --url http://127.0.0.1:3000 --token bbae0f28-d3dd-4820-bf61-8f4bb40815da
```

This will update `~/.dstack/config.yml` allowing the CLI and API to connect to the server by default.

## Environment variables

Here's the list of environment variables which you can override:

- `DSTACK_SERVER_DIR` – (Optional) The path to the directory where the `dstack` server stores the state. Defaults to `/root/.dstack/server`.
- `DSTACK_DATABASE_URL` – (Optional) The database URL to use instead of default SQLite. Currently `dstack` supports Postgres. Example: `postgresql+asyncpg://myuser:mypassword@localhost:5432/mydatabase`.
- `DSTACK_SERVER_ADMIN_TOKEN` – (Optional) The default token of the `admin` user. By default, it's generated randomly
  at the first startup.

## Persist state

By default, `dstack` stores its state in `~/.dstack/server/data` using SQLite.
To use a database, set the `DSTACK_DATABASE_URL` environment variable (see below).

### Replicate SQLite state via Litestream

If not using `DSTACK_DATABASE_URL`, you can still replicate the state to cloud object storage using Litestream. To do
this, you need to set the following environment variables.

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

_**️Note:** The use of Litestream requires that only one instance of the `dstack` server is running at a time._

## Workload log storage

By default, `dstack` stores workload logs in `~/.dstack/server/projects/<project_name>/logs`.

To use AWS CloudWatch Logs, set the `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP` and optionally
the `DSTACK_SERVER_CLOUDWATCH_LOG_REGION` environment variables. The log group must be created beforehand,
`dstack` won't try to create it.

The following permissions are required: `logs:DescribeLogStreams`, `logs:CreateLogStream`, `logs:GetLogEvents`, `logs:PutLogEvents`.

<details>
  <summary>AWS IAM Policy example</summary>

  Given:

  - AWS Account ID: 112233445566
  - `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP=dstack-runs`
  - `DSTACK_SERVER_CLOUDWATCH_LOG_REGION=eu-west-1`

  Policy:

  ```json
  {
      "Version": "2012-10-17",
      "Statement": [
          {
              "Sid": "DstackLogStorageAllow",
              "Effect": "Allow",
              "Action": [
                  "logs:DescribeLogStreams",
                  "logs:CreateLogStream",
                  "logs:GetLogEvents",
                  "logs:PutLogEvents"
              ],
              "Resource": [
                  "arn:aws:logs:eu-west-1:112233445566:log-group:dstack-runs",
                  "arn:aws:logs:eu-west-1:112233445566:log-group:dstack-runs:*"
              ]
          }
      ]
  }
  ```

</details>

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](https://dstack.ai/examples)
* [Changelog](https://github.com/dstackai/dstack/releases)
* [Discord](https://discord.gg/u8SmfwPpMd)
 
##  License

[Mozilla Public License 2.0](https://github.com/dstackai/dstack/blob/master/LICENSE.md)