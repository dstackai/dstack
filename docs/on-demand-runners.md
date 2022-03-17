# On-demand runners

If you provide `dstack` with the credentials to your cloud account and configure limits, 
`dstack` will be able to set up on-demand runners to run your workflows automatically. 

!!! warning "Supported cloud vendors"
    This tutorial describes how to use the on-demand runners with AWS. 
    If you want to use on-demand runners with cloud vendor (such as GCP, Azure, or some other), please write to 
    [hello@dstack.ai](mailto:hello@dstack.ai).

!!! info "How on-demand runners work"

    1. You provide `dstack` credentials to create EC2 instances in your AWS account.
    2. You define what types of EC2 instances `dstack` is allowed to use, spot or on-demand, and what maximum number 
    of each instance type is allowed to run at one time.
    3. When you submit a workflow, `dstack` will create required EC2 instances automatically.
    4. When the workflows are finished and there is no need in on-demand runners, `dstack` will tears them down.

## AWS credentials

Before you'll be able to use on-demand runners, you have to provide `dstack` the credentials
to your AWS account. 

This can be done by the `dstack aws config` command:

```bash
dstack aws config
AWS Access Key ID:  
AWS Secret Access Key: 
Region name:
Artifact S3 bucket[None]: 
```

Note, `Artifact S3 bucket` is optional and has to be specified only if you want to use your own S3 bucket to store 
artifacts.

!!! info "Required IAM permissions"
    The `dstack on-demand` feature requires the following permissions:

    ```
    ec2:Describe*
    ec2:RequestSpotInstances
    ec2:TerminateInstances
    ec2:CancelSpotInstanceRequests
    ec2:CreateSecurityGroups
    ec2:AuthorizeSecurityGroupIngress
    ec2:AuthorizeSecurityGroupEgress
    ```

## Limits

With `dstack`, it's possible to configure what instance types it's allowed to use, spot or on-demand, 
and what maximum number of each instance type is allowed to run at one time.

### Add or change a limit

Type the following to see how the command `dstack limit` works:

```bash
dstack on-demand limit --help
usage: dstack on-demand limit [-h] [--region REGION] --instance-type INSTANCE_TYPE [--spot] [--max MAX]
                              [--delete] [--force]

optional arguments:
  -h, --help            show this help message and exit
  --region REGION, -r REGION
                        Region name
  --instance-type INSTANCE_TYPE, -i INSTANCE_TYPE
                        Instance type
  --spot                Spot purchase type
  --max MAX, -m MAX     Maximum number of instances
  --delete              Delete limit
  --force, -f           Don't ask for confirmation
```

The command has two required arguments: `--instance-type INSTANCE_TYPE` and `--max MAX`.
The `INSTANCE_TYPE` value can be any of the [instance types](https://aws.amazon.com/ec2/instance-types/)
supported by AWS in the corresponding region for the corresponding purchase type.
The `MAX` value can be any integer number. It specifies the maximum number of spot instances
allowed to create per the region, instance type, and purchase type.

The `--spot` argument should be used if you want the `spot` purchase type should be used for the corresponding limit. 

!!! info "Default region"
    Note, the `--region REGION` argument is optional. If it's not provided, the region configured with `dstack config`
    is going to be used.

Here's an example of the command that allows `dstack` to run in parallel up to one spot instance with the type `m5.xlarge`.
    
```bash
dstack on-demand limit --instance-type m5.xlarge --spot --max 1
```
    
If you try to add an instance type that is not supported by your AWS account, you'll see an error.

### Show limits

In order to see the list of current limits, use the following commands:

```bash
dstack on-demand limits
```

Here's an example of the output of this command:

```bash
REGION     INSTANCE TYPE    PURCHASE TYPE      MAXIMUM
eu-west-1  m5.xlarge        spot                     1
```

### Delete limits

In order to delete a limit, use the `dstack on-demand limit --delete` command.

```bash
dstack on-demand limit --instance-type m5.xlarge --spot --delete
```

This command will delete the limit for the corresponding region, instance type, and purchase type. 

!!! warning "Effect" 
    As soon as you decrease or delete a limit, `dstack` will immediately shut down extra instances to match
    the maximum number of allowed limit.

If you want to delete all limits at once, use the following command:

```bash
dstack on-demand limits --delete-all
```

### Disable and enable on-demand runners

You can disable and enable on-demand runners with a single command:

```bash
dstack on-demand disable
```

or 

```bash
dstack on-demand enable
```

!!! warning "Effect"
    If you disable on-demand runners, `dstack` will immediately shut down all running instances.

To see whether on-demand runners are enabled or not, use the following command:

```bash
dstack on-demand status
```

