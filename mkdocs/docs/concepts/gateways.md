---
title: Gateways
description: Managing ingress traffic and endpoints for services
---

# Gateways

Gateways manage ingress traffic for running [services](services.md), handle auto-scaling and rate limits, enable HTTPS, and allow you to configure a custom domain.

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

 NAME             BACKEND          HOSTNAME       DOMAIN       DEFAULT  STATUS
 example-gateway  aws (eu-west-1)  34.244.128.46  example.com  ✓        running
```

</div>

## Configuration options

### Domain

A gateway requires a `domain` to be specified in the configuration before creation. The domain is used to generate service endpoints (e.g. `<run name>.<gateway domain>`).

Once the gateway is created and assigned a hostname, configure your DNS by adding a wildcard record for `*.<gateway domain>` (e.g. `*.example.com`). The record should point to the gateway's hostname and should be of type `A` if the hostname is an IP address (most cases), or of type `CNAME` if the hostname is another domain (load balancers, Kubernetes).

??? info "Project name interpolation"
    You can use the `${{ run.project_name }}` variable to include the service’s project name in the domain name. This is especially useful when [exporting](exports.md) the gateway to multiple projects, as it ensures each importer receives a unique domain name.

    ```yaml
    type: gateway
    name: global-gateway
    backend: aws
    region: eu-west-1
    domain: ${{ run.project_name }}.mycompany.example
    ```

### Backend

You can create gateways with the `aws`, `azure`, `gcp`, or `kubernetes` backends, but that does not limit where services run. A gateway can use one backend while services run on any other backend supported by dstack, including backends where gateways themselves cannot be created.

??? info "Kubernetes"
    Gateways in `kubernetes` backend require an external load balancer. Managed Kubernetes solutions usually include a load balancer.
    For self-hosted Kubernetes, you must provide a load balancer by yourself.

### Load balancer

The optional `load_balancer` property allows you to provision a load balancer in front of the gateway, which is useful for balancing requests between multiple gateway [replicas](#replicas), or for using certain [certificate](#certificate) types, such as AWS ACM.

Currently, only AWS Application Load Balancer (ALB) is supported:

<div editor-title="gateway.dstack.yml">

```yaml
type: gateway
name: example-gateway
backend: aws
region: eu-west-1
domain: example.com
replicas: 2
load_balancer:
  type: alb
certificate:
  type: acm
  arn: arn:aws:acm:eu-west-1:164099421079:certificate/3670388f-f43b-4872-aaf8-907b107a170d
```

</div>

??? info "Requirements"
    An ALB gateway requires:

    - The `aws` backend.
    - Either `certificate: { type: acm, ... }` or `certificate: null`.
    - A VPC with at least two subnets in different availability zones. If `public_ip: False`, subnets must be private and have a route to a NAT gateway.

The provisioned load balancer provides a hostname you can add to your DNS records. Replica hostnames do not need to be added to DNS.

<div class="termy">

```
$ dstack gateway list
 NAME             BACKEND          HOSTNAME                                                  DOMAIN       DEFAULT  STATUS
 example-gateway                   dstack-6t7i1b03-lb-338524206.eu-west-1.elb.amazonaws.com  example.com  ✓        running
    replica=0     aws (eu-west-1)  34.246.162.72                                                                   running
    replica=1     aws (eu-west-1)  52.18.222.190                                                                   running
```

</div>

### Certificate

By default, when you run a service with a gateway, `dstack` provisions an SSL certificate via Let's Encrypt for the configured domain. This automatically enables HTTPS for the service endpoint.

If you disable [public IP](#public-ip) (e.g. to make the gateway private) or if you simply don't need HTTPS, you can set `certificate` to `null`. 

> Note, by default services set [`https`](../reference/dstack.yml/service.md#https) to `true` which requires a certificate. You can set `https` to `auto` to detect if the gateway supports HTTPS or not automatically.

??? info "Certificate types"
    `dstack` supports the following certificate types:

    * `lets-encrypt` (default) — Automatic certificates via [Let's Encrypt](https://letsencrypt.org/). Requires a [public IP](#public-ip).
    * `acm` — Certificates managed by [AWS Certificate Manager](https://aws.amazon.com/certificate-manager/). AWS-only. TLS is terminated at the load balancer, not at the gateway, and HTTP requests are redirected to HTTPS by the ALB.
      Implies `load_balancer: { type: alb }`.
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

### Replicas

A gateway can have multiple replicas for improved availability.

<div editor-title="gateway.dstack.yml">

```yaml
type: gateway
name: example-gateway

backend: aws
region: eu-west-1

domain: example.com

certificate: null
replicas: 2
```

</div>

To balance requests between gateway replicas, add DNS records for each replica, use a natively-supported [load balancer](#load-balancer), or set up a load balancer outside of `dstack`. Replica hostnames are displayed in `dstack` CLI and UI.

<div class="termy">

```shell
$ dstack gateway list
 NAME             BACKEND          HOSTNAME        DOMAIN       DEFAULT  STATUS
 example-gateway                                   example.com  ✓        running
    replica=0     aws (eu-west-1)  34.244.128.46                         running
    replica=1     aws (eu-west-1)  18.201.201.174                        running
```

</div>

!!! warning "Experimental"
    Replicated gateways are an experimental feature and currently have limitations:

    - HTTPS is only supported for AWS gateways with the `acm` [certificate type](#certificate). For other gateways, use an external load balancer for TLS termination.
    - All replicas are bound to the same backend and region.
    - At most 3 replicas are allowed per gateway.

!!! info "Reference"
    For all gateway configuration options, refer to the [reference](../reference/dstack.yml/gateway.md).

## Export gateways

Gateways can be exported to other projects, allowing those projects to use the exported gateways
for running services. See [Exports](exports.md) for more details.

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
