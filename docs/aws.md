# Configure an AWS account

With `dstack` it's possible to run workflows in on-demand runners in your own AWS cloud as well as to store output 
artifacts in your own S3 bucket.

In order to connect `dstack` to your AWS account, run the `dstack aws config` command and specify the credentials 
for your AWS account and, optionally, the name of your S3 bucket that you'd like to use to store output artifacts:

```
dstack aws config
AWS Access Key ID:  
AWS Secret Access Key: 
Region name:
Artifact S3 bucket[None]: 
```

## Required permissions

If you plan to use on-demand runners in your AWS account (via `dstack on-demand`) you'll need the 
following IAM permissions:

```
ec2:Describe*
ec2:RequestSpotInstances
ec2:TerminateInstances
ec2:CancelSpotInstanceRequests
ec2:CreateSecurityGroups
ec2:AuthorizeSecurityGroupIngress
ec2:AuthorizeSecurityGroupEgress
```

To learn how to run workflows in on-demand runners, [read here](on-demand-runners.md).

### Artifact S3 bucket

If you've specified `Artifact S3 bucket`, you'll also need the following permissions for this bucket:

```
s3:GetObject
s3:ListBucket
s3:PutObject
s3:ListObject
```