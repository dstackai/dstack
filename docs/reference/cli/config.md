# config

The `config` command configures the backend of the dstack CLI:

 * In which S3 bucket, to store the state and the artifacts
 * In what region, to create cloud instances.

Use this command before running any other commands. 

### Usage

```shell
dstack config
Configure AWS backend:

AWS profile name (default):
S3 bucket name:
Region name:
```

Make sure to choose a unique S3 bucket name. If the bucket doesn't exist, dstack will prompt you
to create it. 

The command will also create the necessary IAM instance profile role to be used when provisioning EC2 instances.

The configuration is stored in `~/.dstack/config.yaml`.