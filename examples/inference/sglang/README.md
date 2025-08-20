# SGLang

This example shows how to deploy DeepSeek-R1-Distill-Llama 8B and 70B using [SGLang :material-arrow-top-right-thin:{ .external }](https://github.com/sgl-project/sglang){:target="_blank"} and `dstack`.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Deployment
Here's an example of a service that deploys DeepSeek-R1-Distill-Llama 8B and 70B using SgLang.

=== "AMD"

    <div editor-title="examples/inference/sglang/amd/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1-amd

    image: lmsysorg/sglang:v0.4.1.post4-rocm620
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    commands:
      - python3 -m sglang.launch_server
         --model-path $MODEL_ID
         --port 8000
         --trust-remote-code

    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    resources:
      gpu: MI300x
      disk: 300GB
    ```
    </div>

=== "NVIDIA"

    <div editor-title="examples/inference/sglang/nvidia/.dstack.yml">

    ```yaml
    type: service
    name: deepseek-r1-nvidia

    image: lmsysorg/sglang:latest
    env:
      - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-8B

    commands:
      - python3 -m sglang.launch_server
         --model-path $MODEL_ID
         --port 8000
         --trust-remote-code

    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-8B

    resources:
       gpu: 24GB
    ```
    </div>


### Applying the configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply.md) command.

<div class="termy">

```shell
$ dstack apply -f examples/llms/deepseek/sglang/amd/.dstack.yml

 #  BACKEND  REGION     RESOURCES                         SPOT  PRICE
 1  runpod   EU-RO-1   24xCPU, 283GB, 1xMI300X (192GB)    no    $2.49

Submit the run deepseek-r1-amd? [y/n]: y

Provisioning...
---> 100%
```
</div>

Once the service is up, the model will be available via the OpenAI-compatible endpoint
at `<dstack server URL>/proxy/models/<project name>/`.

<div class="termy">

```shell
curl http://127.0.0.1:3000/proxy/models/main/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;dstack token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
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
      "stream": true,
      "max_tokens": 512
    }'
```
</div>

When a [gateway](https://dstack.ai/docs/concepts/gateways/) is configured, the OpenAI-compatible endpoint
is available at `https://gateway.<gateway domain>/`.

## Source code

The source-code of this example can be found in
[`examples/llms/deepseek/sglang` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek/sglang){:target="_blank"}.

## What's next?

1. Check [services](https://dstack.ai/docs/services)
2. Browse the [SgLang DeepSeek Usage](https://docs.sglang.ai/references/deepseek.html), [Supercharge DeepSeek-R1 Inference on AMD Instinct MI300X](https://rocm.blogs.amd.com/artificial-intelligence/DeepSeekR1-Part2/README.html)
