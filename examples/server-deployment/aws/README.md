# Deploy server via AWS CloudFormation

The [cloudformation.yaml](cloudformation.yaml) template deploys `dstack` server
using ECS.

> [!NOTE]
> 1. The template creates a public VPC.
> 2. The template doesn't configure HTTPS.
> 3. Until [#1940](https://github.com/dstackai/dstack/issues/1940) is fixed, always manually set the `AdminToken`
     parameter.

Once, the stack is created, go to `Outputs` for the server URL and admin token.