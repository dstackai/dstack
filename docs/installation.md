Use pip to install the `dstack` CLI:

```shell
pip install dstack
```

## AWS credentials

When you run workflows via the `dstack` CLI, dstack provisions compute resources
and saves data in your AWS account.

The `dstack` CLI needs your AWS account credentials to be configured locally 
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables).

[//]: # (To use the CLI with AWS, dstack requires the following permissions: `ec2:*`, `iam:*`, `secretsmanager:*`, `s3:*`, and `logs:*`.)

If you don't have an AWS account, you can quickly [create](https://aws.amazon.com/resources/create-account/) one,
and get [credentials](https://docs.aws.amazon.com/sdk-for-javascript/v2/developer-guide/getting-your-credentials.html).

!!! info "NOTE:"
    Support for other cloud providers, such as GCP and Azure is in the roadmap.

## Configure AWS region and S3 bucket

Before you can use the `dstack` CLI, you need to run the [`dstack config`](reference/cli/config.md) command.

```shell
dstack config
```

This command will help you configure the AWS region, where dstack will provision compute resources, and
the S3 bucket, where dstack will save data.

```shell
Region name (eu-west-1):
S3 bucket name (dstack-142421590066-eu-west-1):
```

!!! warning "NOTE:"
    Make sure to use an S3 bucket name that isn't used by other AWS accounts.

The configuration will be saved in the `~/.dstack/config.yaml` file.

[//]: # (## Environment variables)
[//]: # ()
[//]: # (Instead of using the `dstack config` command, you can specify the )
[//]: # (`DSTACK_AWS_REGION` and `DSTACK_AWS_S3_BUCKET` environment variables directly.)