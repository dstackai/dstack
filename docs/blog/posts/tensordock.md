---
title: "World's cheapest GPUs with TensorDock and dstack"
date: 2023-10-31
description: "With dstack 0.12.2, you can now effortlessly orchestrate TensorDock's cloud GPUs, leveraging their highly competitive pricing."
slug: "tensordock"
categories:
- Releases
---

# World's cheapest GPUs with TensorDock and dstack 

__With v0.12.2, you can now use cloud GPU at highly competitive pricing using TensorDock.__

At `dstack`, we remain committed to our mission of building the most convenient tool for orchestrating generative AI
workloads in the cloud. In today's release, we have added support for TensorDock, making it easier for you to leverage
cloud GPUs at highly competitive prices.

<!-- more -->

Configuring your TensorDock account with `dstack` is very easy. Simply generate an authorization key in your TensorDock
API settings and set it up in `~/.dstack/server/config.yml`:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: tensordock
    creds:
      type: api_key
      api_key: 248e621d-9317-7494-dc1557fa5825b-98b
      api_token: FyBI3YbnFEYXdth2xqYRnQI7hiusssBC
```

</div>

Now you can restart the server and proceed to using the CLI or API for running development environments, tasks, and services.

<div class="termy">

```shell
$ dstack run . -f .dstack.yml --gpu 40GB

 Min resources  1xGPU (40GB)
 Max price      -
 Max duration   6h
 Retry policy   no

 #  REGION        INSTANCE  RESOURCES                     SPOT  PRICE
 1  unitedstates  ef483076  10xCPU, 80GB, 1xA6000 (48GB)  no    $0.6235
 2  canada        0ca177e7  10xCPU, 80GB, 1xA6000 (48GB)  no    $0.6435
 3  canada        45d0cabd  10xCPU, 80GB, 1xA6000 (48GB)  no    $0.6435
    ...

Continue? [y/n]:
```

</div>

TensorDock offers cloud GPUs on top of servers from dozens of independent hosts, providing some of the most affordable
[GPU pricing](https://tensordock.com/product-marketplace) you can find on the internet.

With `dstack`, you can now utilize TensorDock's GPUs through a highly convenient interface, which includes the
developer-friendly CLI and API.

!!! info "Feedback and support"
    Feel free to ask questions or seek help in our 
    [Discord server](https://discord.gg/u8SmfwPpMd).