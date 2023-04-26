# dstack config

This command configures a remote backend. The configuration is stored in `~/.dstack/config.yaml`.

## Usage

<div class="termy">

```shell
$ dstack config
```

</div>

It will ask first you for a remote type. Currently, `dstack` supports AWS and GCP as remotes.
The next steps vary depending on the remote type.

## AWS

The command will ask you to choose an AWS profile (to take the AWS credentials from), 
an AWS region (must be the same for the S3 bucket), and the name of the S3 bucket. For example:

<div class="termy">

```shell
$ dstack config

? Choose backend: aws
? AWS profile: default
? Choose AWS region: eu-west-1
? Choose S3 bucket: dstack-142421590066-eu-west-1
? Choose EC2 subnet: no preference
```

</div>

## GCP

The command will ask you for a path to the a service account key, GCP region and zone, and storage bucket name. For example:

<div class="termy">

```shell
$ dstack config

? Choose backend: gcp
? Enter path to credentials file: ~/Downloads/dstack-d7735ca1dd53.json
? Choose GCP geographic area: North America
? Choose GCP region: us-west1
? Choose GCP zone: us-west1-b
? Choose storage bucket: dstack-dstack-us-west1
? Choose VPC subnet: no preference
```

</div>