# Gateways

Gateways manage ingress traffic for running [services](services.md), handle auto-scaling and rate limits, enable HTTPS, and allow you to configure a custom domain. They also support custom routers, such as the [SGLang Model Gateway](https://docs.sglang.ai/advanced_features/router.html#).

<!-- > If you're using [dstack Sky](https://sky.dstack.ai),
> the gateway is already set up for you. -->

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

## Configuration options

### Backend

You can create gateways with the `aws`, `azure`, `gcp`, or `kubernetes` backends, but that does not limit where services run. A gateway can use one backend while services run on any other backend supported by dstack, including backends where gateways themselves cannot be created.

??? info "Kubernetes"
    Gateways in `kubernetes` backend require an external load balancer. Managed Kubernetes solutions usually include a load balancer.
    For self-hosted Kubernetes, you must provide a load balancer by yourself.

### Instance type

By default, `dstack` provisions a small, low-cost instance for the gateway. If you expect to run high-traffic services, you can configure a larger instance type using the `instance_type` property.

<div editor-title="gateway.dstack.yml">

```yaml
type: gateway
name: example-gateway

backend: aws
region: eu-west-1

# (Optional) Override the gateway instance type
instance_type: t3.large

domain: example.com
```

</div>

### Router

By default, the gateway uses its own load balancer to route traffic between replicas. However, you can delegate this responsibility to a specific router by setting the `router` property. Currently, the only supported external router is `sglang`.

#### SGLang

The `sglang` router delegates routing logic to the [SGLang Model Gateway](https://docs.sglang.ai/advanced_features/router.html#).

To enable it, set `type` field under `router` to `sglang`:

<div editor-title="gateway.dstack.yml">

```yaml
type: gateway
name: sglang-gateway

backend: aws
region: eu-west-1

domain: example.com

router:
  type: sglang
  policy: cache_aware
```

</div>

!!! info "Policy"
    The `policy` property allows you to configure the routing policy:

    * `cache_aware` &mdash; Default policy; combines cache locality with load balancing, falling back to shortest queue. 
    * `power_of_two` &mdash; Samples two workers and picks the lighter one.                                               
    * `random` &mdash; Uniform random selection.                                                                    
    * `round_robin` &mdash; Cycles through workers in order.                                                             


> Currently, services using this type of gateway must run standard SGLang workers. See the [example](../../examples/inference/sglang/index.md).
>
> Support for prefill/decode disaggregation and auto-scaling based on inter-token latency is coming soon.

### Public IP

If you don't need/want a public IP for the gateway, you can set the `public_ip` to `false` (the default value is `true`), making the gateway private.
Private gateways are currently supported in `aws` and `gcp` backends.

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
