# dstack config

This command configures the AWS region and S3 bucket, where dstack will provision compute resources and save data.

## Usage

```shell
dstack config
```

Make sure to use an S3 bucket name that isn't used by other AWS accounts.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

The configuration is stored in `~/.dstack/config.yaml`.