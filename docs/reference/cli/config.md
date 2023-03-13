# dstack config

This command configures a remote backend. The configuration is stored in `~/.dstack/config.yaml`.

## Usage

```shell
dstack config
```

It will ask first you for a remote type. Currently, `dstack` supports AWS and GCP as remotes.
The next steps vary depending on the remote type.

### AWS

The command will ask you to choose an AWS profile (to take the AWS credentials from), 
an AWS region (must be the same for the S3 bucket), and the name of the S3 bucket. For example:

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

### GCP

The command will ask you for a path to the a service account key, GCP region and zone, and storage bucket name. For example:

```
Path to credentials file: ~/Projects/dstack/my-sa-key.json
GCP geographic area: North America
GCP region: us-central1
GCP zone: us-central1-c
Storage bucket: dstack-test
VPC subnet: default
```
