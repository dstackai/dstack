---
title: "Accessing the GPU marketplace with Vast.ai and dstack"
date: 2023-11-21
description: "With dstack 0.12.3, you can now develop, train and deploy gen AI models using affordable cloud GPUs."
slug: "vastai"
categories:
- Releases
---

# Accessing the GPU marketplace with Vast.ai and dstack

__With dstack 0.12.3, you can now use Vast.ai's GPU marketplace as a cloud provider.__

`dstack` simplifies gen AI model development and deployment through its developer-friendly CLI and API. 
It eliminates cloud infrastructure hassles while supporting top cloud providers (such as AWS, GCP,
Azure, among others).

While `dstack` streamlines infrastructure challenges, GPU costs can still hinder development. To address this, 
we've integrated `dstack` with [Vast.ai](https://vast.ai/), a marketplace providing GPUs from independent hosts at 
notably lower prices compared to other providers.

<!-- more -->

With the `dstack` 0.12.3 release, it's now possible use Vast.ai alongside other cloud providers.

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

By default, it suggests GPU instances based on their quality score. If you want to, you can control the maximum price.

You can use Vast.ai to [fine-tune](../../docs/guides/fine-tuning.md), and 
[deploy](../../docs/guides/text-generation.md) models or
launch [dev environments](../../docs/guides/dev-environments.md) (which are highly convenient for interactive coding with your favorite IDE).

Configuring Vast.ai for use with `dstack` is easy. Log into your [Vast AI](https://cloud.vast.ai/) account, click `Account` in the sidebar,
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

If you want an easy way to 
develop, train and deploy gen AI models using affordable cloud GPUs, 
give `dstack` with Vast.ai a try.

!!! info "Feedback and support"
    Feel free to ask questions or seek help in our 
    [Discord server](https://discord.gg/u8SmfwPpMd).

> Lastly, take the time to check out the preview of the new [fine-tuning](../../docs/guides/fine-tuning.md) and 
[text generation](../../docs/guides/text-generation.md) APIs.