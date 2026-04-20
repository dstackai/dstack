---
title: NVIDIA NIM
description: Deploying Nemotron-3-Super-120B-A12B using NVIDIA NIM
---

# NVIDIA NIM

This example shows how to deploy Nemotron-3-Super-120B-A12B using [NVIDIA NIM](https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html) and `dstack`.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Deployment

Here's an example of a service that deploys Nemotron-3-Super-120B-A12B using NIM.

<div editor-title="nemotron120.dstack.yml">

```yaml
type: service
name: nemotron120

image: nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b:1.8.0
env:
  - NGC_API_KEY
registry_auth:
  username: $oauthtoken
  password: ${{ env.NGC_API_KEY }}
port: 8000
model: nvidia/nemotron-3-super-120b-a12b
volumes:
  - instance_path: /root/.cache/nim
    path: /opt/nim/.cache
    optional: true

resources:
  cpu: x86:96..
  memory: 512GB..
  shm_size: 16GB
  disk: 500GB..
  gpu: H100:80GB:8
```
</div>

### Running a configuration

Save the configuration above as `nemotron120.dstack.yml`, then use the
[`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ NGC_API_KEY=...
$ dstack apply -f nemotron120.dstack.yml
```
</div>

If no gateway is created, the service endpoint will be available at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/services/main/nemotron120/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "nvidia/nemotron-3-super-120b-a12b",
      "messages": [
        {
          "role": "system",
          "content": "You are a helpful assistant."
        },
        {
          "role": "user",
          "content": "What is Deep Learning?"
        }
      ],
      "max_tokens": 128
    }'
```

</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured, the service endpoint will be available at `https://nemotron120.<gateway domain>/`.

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [Nemotron-3-Super-120B-A12B model page](https://build.nvidia.com/nvidia/nemotron-3-super-120b-a12b)
