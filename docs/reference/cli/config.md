# dstack config

This command configures the AWS region and S3 bucket, where dstack will provision compute resources and save data.

### Usage

```shell
dstack config [--aws-profile NAME]
```

Make sure to use an S3 bucket name that isn't used by other AWS accounts.

```shell
Region name (eu-west-1):
S3 bucket name (dstack-142421590066-eu-west-1):
```

The configuration is stored in `~/.dstack/config.yaml`.

#### Arguments reference

The following arguments are optional:

- `--aws-profile NAME` - (Optional) A name of the AWS profile. Default is `default`.