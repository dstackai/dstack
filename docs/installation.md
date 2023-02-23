## Install the CLI

Use `pip` to install `dstack`:

```shell hl_lines="1"
pip install dstack --upgrade
```

!!! info "NOTE:"
    If you only plan to run workflows locally and do not want to share artifacts with others outside your machine, you do
    not need to configure anything else.

## (Optional) Configure a remote

By default, workflows are run locally. If you want to be able to run workflows remotely (e.g. in a configured cloud account),
you have to configure a remote using the `dstack config` command.

!!! info "NOTE:"
    Currently, the only supported remote type is AWS.

### Create an S3 bucket

Before you can use the `dstack config` command, you have to create an S3 bucket in your AWS account 
that you'll use to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create an S3 bucket in the AWS region, where you'd like to run your workflows.

### Configure AWS credentials

The next step is to configure AWS credentials on your local machine so the `dstack` CLI
may perform actions on `s3`, `logs`, `secretsmanager`, `ec2`, and `iam` services.

If you'd like to limit the permissions to the most narrow scope, feel free to use the IAM policy template
below.

??? info "IAM policy template"
    If you're using this template, make sure to replace `{bucket_name}` and `{bucket_name_under_score}` variables
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

### Configure the CLI

Once the AWS credentials are configured, you can configure the CLI:

```shell hl_lines="1"
dstack config
```

This command will ask you to choose an AWS profile (to take the AWS credentials from), 
an AWS region (must be the same for the S3 bucket), and the name of the S3 bucket.

```shell
AWS profile: default
AWS region: eu-west-1
S3 bucket: dstack-142421590066-eu-west-1
EC2 subnet: none
```

The configuration will be saved in the `~/.dstack/config.yaml` file.

Once a remote is configured, you can run workflows remotely and push and pull artifacts.