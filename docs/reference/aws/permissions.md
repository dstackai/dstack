# AWS permissions

The `dstack` CLI needs AWS permissions to provision infrastructure,
and to store metadata, logs, artifacts, and secrets. 

Here's the full list of required permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "*",
      "Resources": [
        "s3://{bucket_name}",
        "s3://{bucket_name}*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:FilterLogEvents",
        "logs:DescribeLogGroups",
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
        "secretsmanager:PutResourcePolicy"
      ],
      "Resource": "arn:*:secretsmanager:*:*:secret:/dstack/{bucket_name}/secrets/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:ListSecrets"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstanceTypes",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeImages",
        "ec2:DescribeInstances",
        "ec2:DescribeSpotInstanceRequests"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:AuthorizeSecurityGroupEgress"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CancelSpotRequests",
        "ec2:TerminateInstances"
      ],
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
        "iam:AttachRolePolicy"
      ],
      "Resource": "arn:aws:iam::*:role/dstack_role_{bucket_name}*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreatePolicy"
      ],
      "Resource": "arn:aws:iam::*:role/dstack_policy_{bucket_name}*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "iam:GetInstanceProfile",
        "iam:CreateInstanceProfile",
        "iam:AddRoleToInstanceProfile"
      ],
      "Resource": "arn:aws:iam::*:role/dstack_role_{bucket_name}*"
    }
  ]
}
```

!!! info "NOTE:"
    Replace `{bucket_name}` substring with the name of the S3 bucket configured in `~/.dstack/config.yaml`.

## Feedback

In case you have questions about permissions, or you want to suggest a change (e.g. on how it works),
please raise a [GitHub issue](https://github.com/dstackai/dstack/issues).

!!! info "NOTE:"
    In `v0.0.12`, we plan to drop the requirement of
    the [`secretsmanager:ListSecrets`](https://github.com/dstackai/dstack/issues/112) and
    [`ec2:DescribeSubnets`](Prompt the user to enter the name of the subnet manually if the user has no access to
    DescribeSubnets #111) permissions. 

