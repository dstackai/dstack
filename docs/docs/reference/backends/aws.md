# AWS

The `AWS` backend type allows provisioning infrastructure and storing artifacts in an AWS account.

Follow the step-by-step guide below to configure this backend in your project.

## Create an S3 bucket

First, you need to create an S3 bucket. `dstack` will use this bucket to store state and artifacts.

!!! info "NOTE:"
    Make sure that the bucket is created in the same region where you plan to provision
    infrastructure.

## Create an IAM user

The next step is to [create an IAM user](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users_create.html) and 
grant this user permissions to perform actions on the `s3`, `logs`, `secretsmanager`, `ec2`, and `iam`
services.

??? info "IAM policy template"
    If you'd like to limit the permissions to the most narrow scope, feel free to use the IAM policy template
    below.

    Replace `{bucket_name}` and `{bucket_name_under_score}` variables in the template below
    with the values that correspond to your S3 bucket.

    For `{bucket_name}`, use the name of the S3 bucket. 
    For `{bucket_name_under_score}`, use the same but with dash characters replaced to underscores 
    (e.g. if `{bucket_name}` is `my-awesome-project`, then  `{bucket_name_under_score}` 
    must be `my_awesome_project`.

    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": [
            "s3:ListAllMyBuckets",
            "s3:GetBucketLocation"
          ],
          "Resource": [
            "arn:aws:s3:::*"
          ]
        },
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
            "secretsmanager:PutSecretValue",
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
            "ec2:DescribeSpotPriceHistory",
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

## Set up AWS credentials

`dstack` support two methods to authenticate with AWS: Default credentials and Access key.

### Default credentials

`dstack` can automatically pick up AWS credentials set up on your machine
(e.g. credentials stored as AWS profiles or environment variables).
You can use default credentials if you don't want to enter and store AWS credentials in `dstack`.

### Access key

`dstack` also support authentication using an access key. To create an access key,
[follow this guide](https://docs.aws.amazon.com/cli/latest/userguide/cli-authentication-user.html#cli-authentication-user-get). Once the access key is created, make sure to download the `.csv` file containing your IAM user's
`Access key ID` and `Secret access key`.

## Configure the backend

Now, log in to the UI, open the project's settings,
click `Edit`, then click `Add backend`, and select `AWS` in the `Type` field.

[//]: # (![]&#40;../../../assets/images/dstack-hub-create-aws-project.png&#41;{ width=800 })

### Fields reference

The following fields are required:

- `Region` - (Required) The region where `dstack` will provision infrastructure and store state and artifacts
- `Bucket` - (Required) The [S3 bucket](#1-create-an-s3-bucket) to store state and artifacts (must be in the same region)

The following arguments are optional:

- `Access key ID` - (Optional) The [Access key ID](#3-create-an-access-key) to authenticate `dstack` 
- `Secret access key` - (Optional) The [Secret access key](#3-create-an-access-key) to authenticate `dstack`
- `Subnet` - (Optional) The EC2 subnet is required to provision infrastructure using a non-default VPC and subnet. If
  not specified, dstack will use the default VPC and subnet.

[//]: # (TODO: Mention on how to manage EC2 quotas)