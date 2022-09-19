Use pip to install the `dstack` CLI:

```shell
pip install dstack
```

## AWS credentials

Make sure the AWS account credentials are configured locally 
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables.)

These credentials are needed by the `dstack` CLI to provision infrastructure and manage state in the cloud. 

[//]: # (To use the CLI with AWS, dstack requires the following permissions: `ec2:*`, `iam:*`, `secretsmanager:*`, `s3:*`, and `logs:*`.)

If you don't have an AWS account, you can quickly [create](https://aws.amazon.com/resources/create-account/) one,
and get [credentials](https://docs.aws.amazon.com/sdk-for-javascript/v2/developer-guide/getting-your-credentials.html). 

## Configure AWS region and S3 bucket

Before you can use the `dstack` CLI, you need to configure the AWS region where dstack will provision 
infrastructure and the S3 bucket where it will save data.

To do that, use the `dstack config` command.

```shell
dstack config
```

It will prompt you to enter an AWS profile name, a region name, and an S3 bucket name.

```shell
AWS profile name (default):
S3 bucket name:
Region name:
```

Make sure to use a name of the S3 bucket that isn't used by other AWS accounts.

The configuration will be saved in the `~/.dstack/config.yaml` file.

[//]: # (## Environment variables)
[//]: # ()
[//]: # (Instead of using the `dstack config` command, you can specify the )
[//]: # (`DSTACK_AWS_REGION` and `DSTACK_AWS_S3_BUCKET` environment variables directly.)