---
title: "dstack 0.10.7: An early preview of services"
date: 2023-08-07
description: "The 0.10.7 update introduces a new configuration type specifically for serving purposes."
slug: "services-preview"
categories:
- Releases
---

# An early preview of services

__The 0.10.7 update introduces a new configuration type for serving.__

Until now, `dstack` has supported `dev-environment` and `task` as configuration types. Even though `task` 
may be used for basic serving use cases, it lacks crucial serving features. With the new update, we introduce
`service`, a dedicated configuration type for serving.

<!-- more -->

Consider the following example:

<div editor-title="text-generation-inference/serve.dstack.yml">

```yaml
type: task

image: ghcr.io/huggingface/text-generation-inference:0.9.3

ports: 
  - 8000

commands: 
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --trust-remote-code
```

</div>

When running it, the `dstack` CLI forwards traffic to `127.0.0.1:8000`.
This is convenient for development but unsuitable for production.

In production, you need your endpoint available on the external network, preferably behind authentication 
and a load balancer. 

This is why we introduce the `service` configuration type.

<div editor-title="text-generation-inference/serve.dstack.yml">

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:0.9.3

port: 8000

commands: 
  - text-generation-launcher --hostname 0.0.0.0 --port 8000 --trust-remote-code
```

</div>

As you see, there are two differences compared to `task`.

1. The `gateway` property: the address of a special cloud instance that wraps the running service with a public
   endpoint. Currently, you must specify it manually. In the future, `dstack` will assign it automatically.
2. The `port` property: A service must always configure one port on which it's running.

When running, `dstack` forwards the traffic to the gateway, providing you with a public endpoint that you can use to
access the running service.

??? info "Existing limitations"
    1. Currently, you must create a gateway manually using the `dstack gateway` command 
    and specify its address via YAML (e.g. using secrets). In the future, `dstack` will assign it automatically.
    2. Gateways do not support HTTPS yet. When you run a service, its endpoint URL is `<the address of the gateway>:80`. 
    The port can be overridden via the port property: instead of `8000`, specify `<gateway port>:8000`.
    3. Gateways do not provide authorization and auto-scaling. In the future, `dstack` will support them as well.

This initial support for services is the first step towards providing multi-cloud and cost-effective inference.

!!! info "Give it a try and share feedback"
    Even though the current support is limited in many ways, we encourage you to give it a try and share your feedback with us!

    More details on how to use services can be found in a [dedicated guide](../../docs/guides/services.md) in our docs. 
    Questions and requests for help are
    very much welcome in our [Discord server](https://discord.gg/u8SmfwPpMd).