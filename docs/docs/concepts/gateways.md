# Gateways

Gateways manage the ingress traffic of running [services](../services.md)
and provide them with an HTTPS endpoint mapped to your domain,
handling authentication, load distribution, and auto-scaling.

> If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
> the gateway is already set up for you.

## Define a configuration

First, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `gateway.dstack.yml`
are both acceptable).

<div editor-title="gateway.dstack.yml"> 

```yaml
type: gateway
# A name of the gateway
name: example-gateway

# Gateways are bound to a specific backend and region
backend: aws
region: eu-west-1

# This domain will be used to access the endpoint
domain: example.com
```

</div>

A domain name is required to create a gateway.

!!! info "Reference"
    See [.dstack.yml](../reference/dstack.yml/gateway.md) for all the options supported by
    gateways, along with multiple examples.

## Create or update a gateway

To create or update the gateway, simply call the [`dstack apply`](../reference/cli/index.md#dstack-apply) command:

<div class="termy">

```shell
$ dstack apply -f gateway.dstack.yml
The example-gateway doesn't exist. Create it? [y/n]: y

 BACKEND  REGION     NAME             HOSTNAME  DOMAIN       DEFAULT  STATUS
 aws      eu-west-1  example-gateway            example.com  ✓        submitted
```

</div>

## Update DNS records

Once the gateway is assigned a hostname, go to your domain's DNS settings
and add a DNS record for `*.<gateway domain>`, e.g. `*.example.com`.
The record should point to the gateway's hostname shown in `dstack`
and should be of type `A` if the hostname is an IP address (most cases),
or of type `CNAME` if the hostname is another domain (some private gateways and Kubernetes).

## Manage gateways

### List gateways

The [`dstack gateway list`](../reference/cli/index.md#dstack-gateway-list) command lists existing gateways and their status.

### Delete a gateway

To delete a gateway, pass gateway configuration to [`dstack delete`](../reference/cli/index.md#dstack-delete):

<div class="termy">

```shell
$ dstack delete -f examples/deployment/gateway.dstack.yml
```

</div>

[//]: # (TODO: Elaborate on default)

[//]: # (TODO: ## Accessing endpoints)

## What's next?

1. See [services](../services.md) on how to run services

!!! info "Reference"
    See [.dstack.yml](../reference/dstack.yml/gateway.md) for all the options supported by
    gateways, along with multiple examples.
