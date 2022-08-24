To use dstack, you'll only need the dstack CLI. No other software needs to be installed or deployed.

The dstack CLI uses your local credentials (e.g. the default AWS environment variables 
or the credentials from `~/.aws/credentials`.) to provision infrastructure and store data.

## Install the CLI

In order to install the CLI, you need to use pip:

```shell
pip install dstack
```

## Configure the backend

Before you can use dstack, you have to configure the dstack backend:

 * In which S3 bucket to store the state and the artifacts
 * In what region, create cloud instances.

To configure this, run the following command:

```shell
dstack config
```

The configuration will be stored in `~/.dstack/config.yaml`:

```yaml
backend: aws
bucket: "my-dstack-workspace"
region: "eu-west-1"
```

!!! info "NOTE:"
    AWS requires all S3 buckets to be unique across all users. Please make sure to choose a unique name.
