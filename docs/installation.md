## Install the CLI

Use `pip` to install `dstack`:

```shell hl_lines="1"
pip install dstack --upgrade
```

!!! info "NOTE:"
    If you only plan to run workflows locally and do not want to share artifacts with others outside your machine, you do
    not need to configure anything else.

## (Optional) Configure the remote

To run workflows remotely (e.g. in the cloud) or share artifacts outside your machine, you must configure your remote 
settings using the `dstack config` command:

```shell hl_lines="1"
dstack config
```

!!! info "NOTE:"
    Currently, the only supported remote type is AWS. 

The `dstack config` command will ask you to choose an AWS profile (which will be used for AWS credentials), an AWS region (where
workflows will be run), and an S3 bucket (to store remote artifacts and metadata).

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

!!! warning "NOTE:"
    Make sure to select an S3 bucket name that isn't used by other AWS accounts.

The configuration will be saved in the `~/.dstack/config.yaml` file.

!!! info "NOTE:"
    An alternative to the `dstack config` command would be configuring the `DSTACK_AWS_S3_BUCKET`,
    and `DSTACK_AWS_EC2_SUBNET` environment variables.
    This might be convenient, if you run `dstack` from your CI/CD pipeline.

[//]: # (TODO: Describe `dstack config --install`)  

### Required AWS credentials

Running workflows remotely requires AWS credentials to be configured on your machine
(e.g. in `~/.aws/credentials` or `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` environment variables).

Here's the full list of AWS permissions the `dstack` CLI needs:

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

!!! info "NOTE:"
    Instead of `{bucket_name}`, use the name of the S3 bucket configured in `~/.dstack/config.yaml`.
    For `{bucket_name_under_score}`, use the same value as for `{bucket_name}` but with dash characters 
    replaced to underscores (e.g. `dstack-142421590066-eu-west-1` becomes `dstack_142421590066_eu_west_1`).