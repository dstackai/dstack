---
title: "Accessing the GPU marketplace with Vast.ai and dstack"
date: 2023-11-21
description: "With dstack 0.12.3, you can now use Vast.ai's GPU marketplace to train and deploy gen AI models."
slug: "vastai"
categories:
- Releases
draft: true
---

# Accessing the GPU marketplace with Vast.ai and dstack

__With dstack 0.12.3, you can now use Vast.ai's GPU marketplace as a cloud provider.__

`dstack` offers a developer-friendly CLI and API to train and deploy gen AI models across any
cloud. It streamlines development and deployment, eliminating the need for cloud infrastructure setup.

The cost of GPUs is often the most critical factor hindering development. To address this, we 
integrated with [Vast.ai](https://vast.ai/), providing GPUs from the marketplace at a lower cost.

<!-- more -->

Vast.ai offers a variety of GPUs from independent hosts and data centers.
By default, it suggests GPU instances based on their quality score. If you want to, you can set the maximum price.

<div class="termy">

```shell
$ dstack run . --gpu 24GB --backend vastai --max-price 0.4

 #  REGION            INSTANCE  RESOURCES                       PRICE
 1  pl-greaterpoland  6244171   16xCPU, 32GB, 1xRTX3090 (24GB)  $0.18478
 2  ee-harjumaa       6648481   16xCPU, 64GB, 1xA5000 (24GB)    $0.29583
 3  pl-greaterpoland  6244172   32xCPU, 64GB, 2xRTX3090 (24GB)  $0.36678
    ...

Continue? [y/n]:
```

</div>

You can use Vast.ai to [fine-tune](../../docs/guides/fine-tuning.md), and 
[deploy](../../docs/guides/text-generation.md) models or
launching [dev environments](../../docs/guides/dev-environments.md) (which are highly convenient for interactive coding with your favorite IDE).
Additionally, you can use Vast.ai alongside other cloud providers, switching to it when needed.

Configuring Vast.ai for use with `dstack` is very easy. Log into your [Vast AI](https://cloud.vast.ai/) account, click Account in the sidebar,
and copy your API Key.

Then, go ahead and configure the backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: vastai
    creds:
      type: api_key
      api_key: d75789f22f1908e0527c78a283b523dd73051c8c7d05456516fc91e9d4efd8c5
```

</div>

Now you can restart the server and proceed to using `dstack`'s CLI and API.

If you've been seeking the simplest way to train and deploy generative AI models utilizing cost-effective cloud GPUs, be
sure to give `dstack` with Vast.ai a try. 

Lastly, take the time to check out the new preview versions of the [fine-tuning](../../docs/guides/fine-tuning.md) and 
[text generation](../../docs/guides/text-generation.md) APIs.

!!! info "Feedback and support"
    Feel free to ask questions or seek help in our 
    [Discord server](https://discord.gg/u8SmfwPpMd).