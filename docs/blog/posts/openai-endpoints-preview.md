---
date: 2024-01-19
description: "Making it easier to deploy custom LLMs as OpenAI-compatible endpoints."
slug: "openai-endpoints-preview"
categories:
  - Releases
---

# dstack 0.14.0: OpenAI-compatible endpoints preview

__Making it easier to deploy custom LLMs as OpenAI-compatible endpoints.__

The `service` configuration deploys any application as a public endpoint. For instance, you can use HuggingFace's 
[TGI](https://github.com/huggingface/text-generation-inference) or other frameworks to deploy custom LLMs. 
While this is simple and customizable, using different frameworks and LLMs complicates the integration of LLMs.

<!-- more -->

With `dstack 0.14.0`, we are extending the `service` configuration in `dstack` to enable you to optionally map your
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

When you deploy the service using `dstack run`, `dstack` will automatically publish the OpenAI-compatible endpoint,
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

Here's a live demo of how it works:

<img src="https://raw.githubusercontent.com/dstackai/static-assets/main/static-assets/images/dstack-openai-python.gif" style="width:100%; max-width: 800px;" />

For more details on how to use the new feature, be sure to check the updated documentation on [services](../../docs/concepts/services.md),
and the [TGI](../../examples/tgi.md) example.

## Migration guide

Note: After you update to `0.14.0`, it's important to delete your existing gateways (if any)
using `dstack gateway delete` and create them again with `dstack gateway create`.

## Feedback

In case you have any questions, experience bugs, or need help, 
drop us a message on our [Discord server](https://discord.gg/u8SmfwPpMd) or submit it as a 
[GitHub issue](https://github.com/dstackai/dstack/issues/new/choose).