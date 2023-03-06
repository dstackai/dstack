## Install the CLI

Use `pip` to install `dstack`:

```shell hl_lines="1"
pip install dstack --upgrade
```

!!! info "NOTE:"
    By default, workflows run locally. If you only plan to run workflows locally and do not want to share artifacts 
    with others outside your machine, you do not need to configure anything else.

## Configure a remote

If you want to be able to run workflows remotely (e.g. in a configured cloud account),
you have to configure a remote using the `dstack config` command. 

Please refer to the specific instructions below for configuring a remote, based on your desired cloud provider.

!!! info "NOTE:"
    Currently, you can configure only AWS and GCP as remotes. Support for Azure, and Hub[^1] are coming soon.

## Configure an AWS remote

### 1. Create an S3 bucket

In order to use AWS as a remote, you first have to create an S3 bucket in your AWS account.
This bucket will be used to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create an S3 bucket in the AWS region where you'd like to run your workflows.

### 2. Configure AWS credentials

The next step is to configure AWS credentials on your local machine. The credentials should grant
the permissions to perform actions on `s3`, `logs`, `secretsmanager`, `ec2`, and `iam` services.

??? info "IAM policy template"
    If you'd like to limit the permissions to the most narrow scope, feel free to use the IAM policy template
    below.

    Replace `{bucket_name}` and `{bucket_name_under_score}` variables in the template below
    with the values that correspond to your S3 bucket.

    For `{bucket_name}`, use the name of the S3 bucket. 
    For `{bucket_name_under_score}`, use the same but with dash characters replaced to underscores 
    (e.g. if `{bucket_name}` is `dstack-142421590066-eu-west-1`, then  `{bucket_name_under_score}` 
    must be `dstack_142421590066_eu_west_1`.

    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
              "s3:PutObject",
              "s3:GetObject",
              "s3:DeleteObject",
              "s3:ListBucket",
              "s3:GetLifecycleConfiguration",
              "s3:PutLifecycleConfiguration",
              "s3:PutObjectTagging",
              "s3:GetObjectTagging",
              "s3:DeleteObjectTagging",
              "s3:GetBucketAcl"
          ],
          "Resource": [
            "arn:aws:s3:::{bucket_name}",
            "arn:aws:s3:::{bucket_name}/*"
          ]
        },
        {
          "Effect": "Allow",
          "Action": [
            "logs:DescribeLogGroups"
          ],
          "Resource": [
            "arn:aws:logs:*:*:log-group:*"
          ]
        },
        {
          "Effect": "Allow",
          "Action": [
            "logs:FilterLogEvents",
            "logs:TagLogGroup",
            "logs:CreateLogGroup",
            "logs:CreateLogStream"
          ],
          "Resource": [
            "arn:aws:logs:*:*:log-group:/dstack/jobs/{bucket_name}*:*",
            "arn:aws:logs:*:*:log-group:/dstack/runners/{bucket_name}*:*"
          ]
        },
        {
          "Effect": "Allow",
          "Action": [
            "secretsmanager:UpdateSecret",
            "secretsmanager:GetSecretValue",
            "secretsmanager:CreateSecret",
            "secretsmanager:PutResourcePolicy",
            "secretsmanager:TagResource",
            "secretsmanager:DeleteSecret"
          ],
          "Resource": [
            "arn:aws:secretsmanager:*:*:secret:/dstack/{bucket_name}/credentials/*",
            "arn:aws:secretsmanager:*:*:secret:/dstack/{bucket_name}/secrets/*"
          ]
        },
        {
          "Effect": "Allow",
          "Action": [
            "ec2:DescribeInstanceTypes",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeSubnets",
            "ec2:DescribeImages",
            "ec2:DescribeInstances",
            "ec2:DescribeSpotInstanceRequests",
            "ec2:RunInstances",
            "ec2:CreateTags",
            "ec2:CreateSecurityGroup",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:AuthorizeSecurityGroupEgress"
          ],
          "Resource": "*"
        },
        {
          "Effect": "Allow",
          "Action": [
            "ec2:CancelSpotInstanceRequests",
            "ec2:TerminateInstances"
          ],
          "Resource": "*",
          "Condition": {
            "StringEquals": {
              "aws:ResourceTag/dstack_bucket": "{bucket_name}"
            }
          }
        },
        {
          "Effect": "Allow",
          "Action": [
            "iam:GetRole",
            "iam:CreateRole",
            "iam:AttachRolePolicy",
            "iam:TagRole"
          ],
          "Resource": "arn:aws:iam::*:role/dstack_role_{bucket_name_under_score}*"
        },
        {
          "Effect": "Allow",
          "Action": [
            "iam:CreatePolicy",
            "iam:TagPolicy"
          ],
          "Resource": "arn:aws:iam::*:policy/dstack_policy_{bucket_name_under_score}*"
        },
        {
          "Effect": "Allow",
          "Action": [
            "iam:GetInstanceProfile",
            "iam:CreateInstanceProfile",
            "iam:AddRoleToInstanceProfile",
            "iam:TagInstanceProfile",
            "iam:PassRole"
          ],
          "Resource": [
            "arn:aws:iam::*:instance-profile/dstack_role_{bucket_name_under_score}*",
            "arn:aws:iam::*:role/dstack_role_{bucket_name_under_score}*"
          ]
        }
      ]
    }
    ```

### 3. Configure the CLI

Once the AWS credentials are configured on your local machine, you can configure the CLI:

```shell hl_lines="1"
dstack config
```

This command will ask you to choose an AWS profile (to take the AWS credentials from), 
an AWS region (must be the same for the S3 bucket), and the name of the S3 bucket.

```shell
Backend: aws
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

That's it! You've configured AWS as a remote.

## Configure a GCP remote

!!! info "NOTE:"
    Support for GCP is experimental. In order to try it, make sure to install the `0.2rc1` version of `dstack`:

    ```shell hl_lines="1"
    pip install dstack==0.2rc1
    ```

### 1. Create a project

In order to use GCP as a remote, you first have to create a project in your GCP account
and make sure that the required APIs and enabled for it.

??? info "Required APIs"
    Here's the list of APIs that have to be enabled for the project.

    ```
    cloudapis.googleapis.com
    compute.googleapis.com 
    logging.googleapis.com
    secretmanager.googleapis.com
    storage-api.googleapis.com
    storage-component.googleapis.com 
    storage.googleapis.com 
    ```

### 2. Create a storage bucket

Once the project is created, you can proceed and create a storage bucket. This bucket
will be used to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create the bucket in the location where you'd like to run your workflows.

### 3. Create a service account

The next step is to create a service account in the created project and configure the 
following roles for it: `Service Account User`, `Compute Admin`, `Storage Admin`, `Secret Manager Admin`, and `Logging Admin`.

### 4. Create a service account key

Once the service account is set up, create a key for it and download the corresponding JSON file
to your local machine (e.g. to `~/Downloads/my-awesome-project-d7735ca1dd53.json`).

### 5. Configure the CLI

Once the service account key JSON file is on your machine, you can configure the CLI:

```shell
dstack config
```

The command will ask you for a path to the a service account key, GCP region and zone, and storage bucket name. For example:

```
Backend: gcp
Path to credentials file: ~/Downloads/my-awesome-project-d7735ca1dd53.json
GCP geographic area: North America
GCP region: us-central1
GCP zone: us-central1-c
Storage bucket: dstack-my-awesome-project
VPC subnet: default
```

That's it! You've configured GCP as a remote.

[^1]:
    Use the `dstack hub start --port PORT` command (coming soon) to host a web application that provides a UI for configuring cloud
    accounts and managing user tokens. Configure this hub as a remote for the CLI to enable the hub to act as a proxy
    between the CLI and the configured account. This setup offers improved security and collaboration.