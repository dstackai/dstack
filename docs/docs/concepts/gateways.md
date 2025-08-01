# Gateways

Gateways manage the ingress traffic of running [services](services.md),
provide an HTTPS endpoint mapped to your domain, handle auto-scaling and rate limits.

> If you're using [dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
> the gateway is already set up for you.

## Apply a configuration

First, define a gateway configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `gateway.dstack.yml` are both acceptable).

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

To create or update the gateway, simply call the [`dstack apply`](../reference/cli/dstack/apply.md) command:

<div class="termy">

```shell
$ dstack apply -f gateway.dstack.yml
The example-gateway doesn't exist. Create it? [y/n]: y

Provisioning...
---> 100%

 BACKEND  REGION     NAME             HOSTNAME  DOMAIN       DEFAULT  STATUS
 aws      eu-west-1  example-gateway            example.com  ✓        submitted
```

</div>

!!! info "Reference"
    For all gateway configuration options, refer to the [reference](../reference/dstack.yml/gateway.md).

## Update DNS records

Once the gateway is assigned a hostname, go to your domain's DNS settings
and add a DNS record for `*.<gateway domain>`, e.g. `*.example.com`.
The record should point to the gateway's hostname shown in `dstack`
and should be of type `A` if the hostname is an IP address (most cases),
or of type `CNAME` if the hostname is another domain (some private gateways and Kubernetes).

## Manage gateways

### List gateways

The [`dstack gateway list`](../reference/cli/dstack/gateway.md#dstack-gateway-list) command lists existing gateways and their status.

### Delete a gateway

To delete a gateway, pass the gateway configuration to [`dstack delete`](../reference/cli/dstack/delete.md):

<div class="termy">

```shell
$ dstack delete -f examples/inference/gateway.dstack.yml
```

</div>

Alternatively, you can delete a gateway by passing the gateway name  to `dstack gateway delete`.

[//]: # (TODO: Elaborate on default)

[//]: # (TODO: ## Accessing endpoints)

!!! info "What's next?"
    1. See [services](services.md) on how to run services
