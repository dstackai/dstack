# Gateways

Gateways handle the ingress traffic of running services. In order to run a service, you need to have at least one
gateway set up.

If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
the gateway is already set up for you.

## Configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `gateway.dstack.yml`
are both acceptable).

<div editor-title="gateway.dstack.yml"> 

```yaml
type: gateway
name: example-gateway

backend: aws
region: eu-west-1
domain: example.com
```

</div>

A domain name is required to create a gateway.

> See the [.dstack.yml reference](../reference/dstack.yml/gateway.md)
> for many examples on gateway configuration.

## Creating and updating gateways

To create or update the gateway, simply call the [`dstack apply`](../reference/cli/index.md#dstack-apply) command:

<div class="termy">

```shell
$ dstack apply . -f examples/deployment/gateway.dstack.yml

The example-gateway doesn't exist. Create it? [y/n]: y

 BACKEND  REGION     NAME             HOSTNAME  DOMAIN       DEFAULT  STATUS
 aws      eu-west-1  example-gateway            example.com  ✓        submitted

```

</div>

## Updating DNS reconds

Once the gateway is assigned a hostname, go to your domain's DNS settings
and add an `A` DNS record for `*.<gateway domain>` (e.g., `*.example.com`) pointing to the gateway's hostname.

This will allow you to access runs and models using this domain.

## Managing gateways

**Destroying gateways**

To delete a gateway, use [`dstack destroy`](../reference/cli/index.md#dstack-destroy):

<div class="termy">

```shell
$ dstack destroy . -f examples/deployment/gateway.dstack.yml
```

</div>

**Listing gateways**

The [`dstack gateway list`](../reference/cli/index.md#dstack-gateway-list) command lists existing gateways and their status.

[//]: # (TODO: Ellaborate on default`)

[//]: # (TODO: ## Accessing endpoints)

## What's next?

1. See [services](services.md) on how to run services
2. Check the [`.dstack.yml` reference](../reference/dstack.yml/gateway.md) for more details and examples