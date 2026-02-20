---
title: Gateways
description: Managing ingress traffic and endpoints for services
---

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

### Domain

A gateway requires a `domain` to be specified in the configuration before creation. The domain is used to generate service endpoints (e.g. `<run name>.<gateway domain>`).

Once the gateway is created and assigned a hostname, configure your DNS by adding a wildcard record for `*.<gateway domain>` (e.g. `*.example.com`). The record should point to the gateway's hostname and should be of type `A` if the hostname is an IP address (most cases), or of type `CNAME` if the hostname is another domain (some private gateways and Kubernetes).

### Backend

You can create gateways with the `aws`, `azure`, `gcp`, or `kubernetes` backends, but that does not limit where services run. A gateway can use one backend while services run on any other backend supported by dstack, including backends where gateways themselves cannot be created.

??? info "Kubernetes"
    Gateways in `kubernetes` backend require an external load balancer. Managed Kubernetes solutions usually include a load balancer.
    For self-hosted Kubernetes, you must provide a load balancer by yourself.

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

### Certificate

By default, when you run a service with a gateway, `dstack` provisions an SSL certificate via Let's Encrypt for the configured domain. This automatically enables HTTPS for the service endpoint.

If you disable [public IP](#public-ip) (e.g. to make the gateway private) or if you simply don't need HTTPS, you can set `certificate` to `null`. 

> Note, by default services set [`https`](../reference/dstack.yml/service.md#https) to `true` which requires a certificate. You can set `https` to `auto` to detect if the gateway supports HTTPS or not automatically.

??? info "Certificate types"
    `dstack` supports the following certificate types:

    * `lets-encrypt` (default) — Automatic certificates via [Let's Encrypt](https://letsencrypt.org/). Requires a [public IP](#public-ip).
    * `acm` — Certificates managed by [AWS Certificate Manager](https://aws.amazon.com/certificate-manager/). AWS-only. TLS is terminated at the load balancer, not at the gateway.
    * `null` — No certificate. Services will use HTTP.

### Public IP

If you don't need a public IP for the gateway, you can set `public_ip` to `false` (the default is `true`), making the gateway private.

Private gateways are currently supported in `aws` and `gcp` backends.

<div editor-title="gateway.dstack.yml">

```yaml
type: gateway
name: private-gateway

backend: aws
region: eu-west-1
domain: example.com

public_ip: false
certificate: null
```

</div>

### Instance type

By default, `dstack` provisions a small, low-cost instance for the gateway. If you expect to run high-traffic services, you can configure a larger instance type using the `instance_type` property.

<div editor-title="gateway.dstack.yml">

```yaml
type: gateway
name: example-gateway

backend: aws
region: eu-west-1

instance_type: t3.large

domain: example.com
```

</div>

!!! info "Reference"
    For all gateway configuration options, refer to the [reference](../reference/dstack.yml/gateway.md).

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
