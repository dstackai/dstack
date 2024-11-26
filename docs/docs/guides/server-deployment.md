The `dstack` server can run anywhere: on your laptop, a dedicated server, or in the cloud.

You can run the server either through `pip` or using Docker.

=== "pip"

    <div class="termy">
    
    ```shell
    $ pip install "dstack[all]" -U
    $ dstack server

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/
    ```
    
    </div>

    > The server can be set up via `pip` on Linux, macOS, and Windows (via WSL 2).
    > It requires Git and OpenSSH.

=== "Docker"

    <div class="termy">
    
    ```shell
    $ docker run -p 3000:3000 \
        -v $HOME/.dstack/server/:/root/.dstack/server \
        dstackai/dstack

    Applying ~/.dstack/server/config.yml...

    The admin token is "bbae0f28-d3dd-4820-bf61-8f4bb40815da"
    The server is running at http://127.0.0.1:3000/
    ```
        
    </div>

=== "CloudFormation"

    If you'd like to deploy the server to a private AWS VPC, you can use 
    our CloudFormation [template :material-arrow-top-right-thin:{ .external }](https://console.aws.amazon.com/cloudformation/home#/stacks/quickcreate?templateURL=https://get-dstack.s3.eu-west-1.amazonaws.com/cloudformation/template.yaml){:target="_blank"}.

    First, ensure, you've set up a private VPC with public and private subnets.

    ![](https://github.com/dstackai/static-assets/blob/main/static-assets/images/dstack-aws-private-vpc-example-v2.png?raw=true)

    Create a stack using the template, and specify the VPC and private subnets.
    Once, the stack is created, go to `Outputs` for the server URL and admin token.

    To access the server URL, ensure you're connected to the VPC, e.g. via VPN client.

    > If you'd like to adjust anything, the source code of the template can be found at
    [`examples/server-deployment/cloudformation/template.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/server-deployment/cloudformation/template.yaml){:target="_blank"}.

## Backend configuration

To use `dstack` with your own cloud accounts, create the `~/.dstack/server/config.yml` file and 
[configure backends](../reference/server/config.yml.md).
The server loads this file on startup. 

Alternatively, you can configure backends on the [project settings page](../concepts/projects/#project-backends) via the control plane's UI.

> For using `dstack` with on-prem servers, no backend configuration is required.
> See [SSH fleets](../concepts/fleets.md#ssh-fleets) for more details.

## State persistence

By default, the `dstack` server stores its state locally in `~/.dstack/server` using SQLite.

??? info "Replicate state to cloud storage"
    If you’d like, you can configure automatic replication of your SQLite state to cloud object storage using Litestream.

    To enable Litestream replication, set the following environment variables:
    
    - `LITESTREAM_REPLICA_URL` - The url of the cloud object storage.
      Examples: `s3://<bucket-name>/<path>`, `gcs://<bucket-name>/<path>`, `abs://<storage-account>@<container-name>/<path>`, etc.
    
    You also need to configure cloud storage credentials.
    
    **AWS S3**
    
    To persist state into an AWS S3 bucket, provide the following environment variables:
    
    - `AWS_ACCESS_KEY_ID` - The AWS access key ID
    - `AWS_SECRET_ACCESS_KEY` -  The AWS secret access key
    
    **GCP Storage**
    
    To persist state into a GCP Storage bucket, provide one of the following environment variables:
    
    - `GOOGLE_APPLICATION_CREDENTIALS` - The path to the GCP service account key JSON file
    - `GOOGLE_APPLICATION_CREDENTIALS_JSON` - The GCP service account key JSON

    **Azure Blob Storage**
    
    To persist state into an Azure blog storage, provide the following environment variable.
    
    - `LITESTREAM_AZURE_ACCOUNT_KEY` - The Azure storage account key
    
    More [details](https://litestream.io/guides/) on options for configuring replication.

### PostgreSQL

To store the state externally, use the `DSTACK_DATABASE_URL` and `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP` environment variables.

??? info "Migrate from SQLite to PostgreSQL"
    You can migrate the existing state from SQLite to PostgreSQL using `pgloader`:

    1. Create a new PostgreSQL database
    2. Clone the `dstack` repo and [install](https://github.com/dstackai/dstack/blob/master/contributing/DEVELOPMENT.md) `dstack` from source.
       Ensure you've checked out the tag that corresponds to your server version (e.g. `git checkout 0.18.10`).
    3. Apply database migrations to the new database:
      ```bash
      cd src/dstack/_internal/server/
      export DSTACK_DATABASE_URL="postgresql+asyncpg://..."
      alembic upgrade head
      ```
    4. Install [pgloader :material-arrow-top-right-thin:{.external }](https://github.com/dimitri/pgloader){:target="_blank"}
    5. Pass the path to the `~/.dstack/server/data/sqlite.db` file to `SOURCE_PATH` and 
       set `TARGET_PATH` with the URL of the PostgreSQL database. Example:
       ```bash
       cd scripts/
       export SOURCE_PATH=sqlite:///Users/me/.dstack/server/data/sqlite.db
       export TARGET_PATH=postgresql://postgres:postgres@localhost:5432/postgres
       pgloader sqlite_to_psql.load
       ```
       The `pgloader` script will migrate the SQLite data to PostgreSQL. It may emit warnings that are safe to ignore. 
       
       If you encounter errors, please [submit an issue](https://github.com/dstackai/dstack/issues/new/choose).

## Logs storage

By default, `dstack` stores workload logs in `~/.dstack/server/projects/<project_name>/logs`.

### AWS CloudWatch

To store logs in AWS CloudWatch, set the `DSTACK_SERVER_CLOUDWATCH_LOG_GROUP` and
the `DSTACK_SERVER_CLOUDWATCH_LOG_REGION` environment variables. 

The log group must be created beforehand, `dstack` won't try to create it.

??? info "Required permissions"

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
                  "arn:aws:logs:::log-group:<group name>",
                  "arn:aws:logs:::log-group:<group name>:*"
              ]
          }
      ]
    }
    ```

## Running multiple replicas of the server

If you'd like to run multiple server replicas, make sure to configure `dstack` to use [PostgreSQL](#postgresql)
and [AWS CloudWatch](#aws-cloudwatch).

## Enabling encryption

If you want backend credentials and user tokens to be encrypted, you can set up encryption keys via
[`~/.dstack/server/config.yml`](../reference/server/config.yml.md#encryption_1).