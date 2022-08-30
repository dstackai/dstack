To use dstack, you'll only need the dstack CLI. No other software needs to be installed or deployed.

!!! info "NOTE:"
    dstack currently works only with **AWS**. If you'd like to use dstack with **GCP**, **Azure**, or **Kubernetes**,
    please [upvote](https://github.com/dstackai/dstack/labels/cloud-provider) the corresponding issue.

## Install the CLI

In order to install the dstack CLI, you need to use **pip**:

```shell
pip install dstack
```

## Configure AWS credentials

The dstack CLI uses your local AWS credentials to provision infrastructure and store data.
Make sure, you've [configured](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-files.html) them
locally before using the dstack CLI. 

The credentials should allow actions on the EC2, IAM, SecretsManager, 
S3, and CloudWatch Logs resources.

## Configure the dstack backend

Before you can use the dstack CLI, you have to configure the dstack backend.

It includes configuring the following:

 * In which S3 bucket to store the state and artifacts
 * In what AWS region, to create EC2 instances

To configure this, run the following command:

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

The final configuration will be stored in `~/.dstack/config.yaml`.

Once the command is successful, you are good to go to run workflows with the CLI.