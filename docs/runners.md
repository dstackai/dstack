# Runners

`Runners` are machines that run submitted `Workflows` and their `Jobs`. dstack supports two types of `Runners`: the `on-demand` `Runners`
and `self-hosted` `Runners`. 

The `on-demand` `Runners` are created automatically by dstack (in the computing vendor, configured by the user, e.g. `AWS`) 
for the time of running `Workflows`. The `self-hosted` `Runners` can be set up manually to run `Workflows`
using the user's own hardware.

## On-demand runners

To use the `on-demand` `Runners`, go to the `Settings`, then `AWS`.

Here, you have to provide `AWS Access Key ID` and `AWS Secret Access Key` that have the
corresponding permissions to create EC2 instances in your `AWS` account:

```
ec2:Describe*
ec2:RequestSpotInstances
ec2:TerminateInstances
ec2:CancelSpotInstanceRequests
ec2:CreateSecurityGroups
ec2:AuthorizeSecurityGroupIngress
ec2:AuthorizeSecurityGroupEgress
```

Once you've provided `Credentials`, use the `Add limit` button to configure limits:

![](images/dstack_on_demand_settings.png){ lazy=true width="1060" }

The configured `Limits` represent the maximum number of EC2 instances of the specific `Instance type` and in the specific `Region`, that
dstack can create at one time to run `Workflows`.

!!! warning ""
    Note, using certain `Instance type` with your computing vendor may require you to request the corresponding 
    `Service Quotes` from their support.

## Self-hosted runners

As an alternative to `on-demand` `Runners`, you can run `Workflows` on your own hardware. 

To do that, you have to run the following command on your server:

```bash
curl -fsSL https://get.dstack.ai/runner -o get-dstack-runner.sh
sudo sh get-dstack-runner.sh
dstack-runner config --token <token>
dstack-runner start
```

Your `token` value can be found in `Settings`:

![](images/dstack_quickstart_token.png){ lazy=true width="1060" }

If you've done this step properly, you'll see your server on the `Runners` page:

![](images/dstack_quickstart_runners.png){ lazy=true width="1060" }

## Limitations

[//]: # (!!! warning "Don't have an AWS account or your own hardware?")
Currently, dstack supports only `AWS`. If you'd like to use dstack with other computing vendors, please upvote the corresponding requests:
[`GCP`](https://github.com/dstackai/dstack/issues/1) and [`Azure`](https://github.com/dstackai/dstack/issues/2).

If you'd like to use dstack with your existing `Kubernetes` cluster, upvote [this request](https://github.com/dstackai/dstack/issues/4).

Finally, if you'd like dstack to manage infrastructure on its own so you can pay directly to dstack for computing 
instances, please upvote [this request](https://github.com/dstackai/dstack/issues/3).