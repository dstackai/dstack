Use pip to install `dstack` locally:

```shell
pip install dstack
```

## AWS credentials

When you run workflows via the `dstack` CLI, dstack provisions compute resources
and saves data in a configured AWS account.

The `dstack` CLI needs your AWS account credentials to be configured locally 
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables).

For more details on what AWS permissions the `dstack` CLI requires, check the [reference](reference/aws/permissions.md) .

!!! info "NOTE:"
    Support for GCP and Azure is in the roadmap.

If you don't have an AWS account, you can quickly [create](https://aws.amazon.com/resources/create-account/) one,
and get [credentials](https://docs.aws.amazon.com/sdk-for-javascript/v2/developer-guide/getting-your-credentials.html).

## Configure AWS region and S3 bucket

Before you can use the `dstack` CLI, you need to run the [`dstack config`](reference/cli/config.md) command.

```shell
dstack config
```

This command configures the AWS region, where dstack will provision compute resources, and
the S3 bucket, where dstack will save data.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

!!! warning "NOTE:"
    Make sure to use an S3 bucket name that isn't used by other AWS accounts.

The configuration will be saved in the `~/.dstack/config.yaml` file.

[//]: # (## Environment variables)
[//]: # ()
[//]: # (Instead of using the `dstack config` command, you can specify the )
[//]: # (`DSTACK_AWS_REGION` and `DSTACK_AWS_S3_BUCKET` environment variables directly.)