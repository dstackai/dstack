# AWS

## 1. Create an S3 bucket

In order to use AWS as a remote, you first have to create an S3 bucket in your AWS account.
This bucket will be used to store workflow artifacts and metadata.

!!! info "NOTE:"
    Make sure to create an S3 bucket in the AWS region where you'd like to run your workflows.

## 2. Configure AWS credentials

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

## 3. Configure the CLI

Once the AWS credentials are configured on your local machine, you can configure the CLI using the `dstack config` command.

This command will ask you to choose an AWS profile, an AWS region (must be the same for the S3 bucket), 
and the name of the S3 bucket.

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

That's it! You've configured AWS as a remote.