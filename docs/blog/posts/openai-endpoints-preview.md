---
title: "dstack 0.14.0rc1: OpenAI-compatible endpoints preview"
date: 2024-01-19
description: "Making it easier to deploy custom LLMs as OpenAI-compatible endpoints."
slug: "openai-endpoints-preview"
categories:
  - Previews
---

# dstack 0.14.0rc1: OpenAI-compatible endpoints preview

__Making it easier to deploy custom LLMs as OpenAI-compatible endpoints.__

The `service` configuration deploys any application as a public endpoint. For instance, you can use HuggingFace's 
[TGI](https://github.com/huggingface/text-generation-inference) or frameworks to deploy 
custom LLMs. While this is simple and customizable, using different frameworks and LLMs complicates 
the integration of LLMs.

<!-- more -->

With the upcoming `dstack 0.14.0`, we are extending the `service` configuration in `dstack` to enable you to optionally map your
custom LLM to an OpenAI-compatible endpoint.

Here's how it works: you define a `service` (as before) and include the `model` property with 
the model's `type`, `name`, `format`, and other settings.

```yaml
type: service

image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - MODEL_ID=mistralai/Mistral-7B-Instruct-v0.1
port: 80
commands:
  - text-generation-launcher --port 80 --trust-remote-code


# Optional mapping for OpenAI-compatible endpoint
model:
  type: chat
  name: mistralai/Mistral-7B-Instruct-v0.1
  format: tgi
```

When you deploy this service using `dstack run`, `dstack` will automatically publish the OpenAI-compatible endpoint,
converting the prompt and response format between your LLM and OpenAI interface.

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://gateway.<your gateway domain>",
    api_key="none"
)

completion = client.chat.completions.create(
    model="mistralai/Mistral-7B-Instruct-v0.1",
    messages=[
        {"role": "user", "content": "Compose a poem that explains the concept of recursion in programming."}
    ]
)

print(completion.choices[0].message)
```

!!! info "NOTE:"
    By default, dstack loads the model's `chat_template` and `eos_token` from Hugging Face. However, you can override them using
    the corresponding properties under `model`.

Here's a live demo of how it works:

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-openai-python.gif" style="width:100%; max-width: 800px;" />

## Try the preview

To try the preview of this new upcoming feature, make sure to install `0.14.0rc1` and restart your server.

```shell
pip install "dstack[all]==0.14.0rc1"
```

## Migration guide

Note: In order to use the new feature, it's important to delete your existing gateway (if any)
using `dstack gateway delete` and then create it again with `dstack gateway create`.

## Why does this matter?

With `dstack`, you can train and deploy models using any cloud providers, easily leveraging GPU availability across
providers, spot instances, multiple regions, and more.

## Feedback

Do you have any questions or need assistance? Feel free to join our [Discord server](https://discord.gg/u8SmfwPpMd).