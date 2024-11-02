# Deploy server to a private VPC via AWS CloudFormation

The [cloudformation.yaml](cloudformation.yaml) template deploys `dstack` server
using ECS.

The template requires specifying an existing VPC with private subnets.

> [!WARNING]
> Until [#1940](https://github.com/dstackai/dstack/issues/1940) is fixed, always manually set the `AdminToken`
> parameter.

Once, the stack is created, go to `Outputs` for the server URL and admin token.

> [!NOTE]
> To access the server URL, ensure you're connected to the VPC, e.g. via VPN client.