# Deploying server to a private VPC via AWS CloudFormation

If you'd like to deploy the server to a private AWS VPC, you can use 
our CloudFormation [template :material-arrow-top-right-thin:{ .external }](https://console.aws.amazon.com/cloudformation/home#/stacks/quickcreate?templateURL=https://get-dstack.s3.eu-west-1.amazonaws.com/cloudformation/template.yaml){:target="_blank"}.

First, ensure, you've set up a private VPC with public and private subnets.

![](https://dstack.ai/static-assets/static-assets/images/dstack-aws-private-vpc-example-v2.png)

Create a stack using the template, and specify the VPC and private subnets.
Once, the stack is created, go to `Outputs` for the server URL and admin token.

> To access the server URL, ensure you're connected to the VPC, e.g. via VPN client.

!!! info "Source code"
    If you'd like to adjust anything, the source code of the template can be found at
    [`examples/server-deployment/cloudformation/template.yaml` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/server-deployment/cloudformation/template.yaml){:target="_blank"}.
