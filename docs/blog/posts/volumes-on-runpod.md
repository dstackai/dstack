---
title: Optimizing inference cold starts on RunPod with volumes
date: 2024-08-13
description: "Learn how to use volumes with dstack to optimize model inference cold start times on RunPod."  
slug: volumes-on-runpod
---

# Optimizing inference cold starts on RunPod with volumes

Deploying custom models in the cloud often faces the challenge of cold start times, including the time to provision a
new instance and download the model. This is especially relevant for services with autoscaling when new model replicas
need to be provisioned quickly. 

Let's explore how `dstack` optimizes this process using volumes, with an example of
deploying a model on RunPod.

<!-- more -->

Suppose you want to deploy Llama 3.1 on RunPod as a [service](../../docs/services.md):

<div editor-title="examples/llms/llama31/tgi/service.dstack.yml">

```yaml
type: service
name: llama31-service-tgi

replicas: 1..2
scaling:
  metric: rps
  target: 30
  
image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_INPUT_LENGTH=4000
  - MAX_TOTAL_TOKENS=4096
commands:
  - text-generation-launcher
port: 80

spot_policy: auto

resources:
  gpu: 24GB

model:
  format: openai
  type: chat
  name: meta-llama/Meta-Llama-3.1-8B-Instruct
```

</div>

When you run `dstack apply`, it creates a public endpoint with one service replica. `dstack` will then automatically scale
the service by adjusting the number of replicas based on traffic.

When starting each replica, `text-generation-launcher` downloads the model to the `/data` folder. For Llama 3.1 8B, this
usually takes under a minute, but larger models may take longer. Repeated downloads can significantly affect
auto-scaling efficiency.

Great news: RunPod supports network volumes, which we can use for caching models across multiple replicas.

With `dstack`, you can create a RunPod volume using the following configuration:

<div editor-title="examples/mist/volumes/runpod.dstack.yml">

```yaml
type: volume
name: llama31-volume

backend: runpod
region: EU-SE-1

# Required size
size: 100GB
```

</div>

Go ahead and create it via `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f examples/mist/volumes/runpod.dstack.yml
```

</div>

Once the volume is created, attach it to your service by updating the configuration file and mapping the 
volume name to the `/data` path.

<div editor-title="examples/llms/llama31/tgi/service.dstack.yml">

```yaml
type: service
name: llama31-service-tgi

replicas: 1..2
scaling:
  metric: rps
  target: 30
  
volumes:
 - name: llama31-volume
   path: /data
  
image: ghcr.io/huggingface/text-generation-inference:latest
env:
  - HUGGING_FACE_HUB_TOKEN
  - MODEL_ID=meta-llama/Meta-Llama-3.1-8B-Instruct
  - MAX_INPUT_LENGTH=4000
  - MAX_TOTAL_TOKENS=4096
commands:
  - text-generation-launcher
port: 80

spot_policy: auto

resources:
  gpu: 24GB
  
model:
  format: openai
  type: chat
  name: meta-llama/Meta-Llama-3.1-8B-Instruct
```

</div>

In this case, `dstack` attaches the specified volume to each new replica. This ensures the model is downloaded only
once, reducing cold start time in proportion to the model size.

A notable feature of RunPod is that volumes can be attached to multiple containers simultaneously. This capability is
particularly useful for autoscalable services or distributed tasks.

Using [volumes](../../docs/concepts/volumes.md) not only optimizes inference cold start times but also enhances the
efficiency of data and model checkpoint loading during training and fine-tuning.
Whether you're running [tasks](../../docs/tasks.md) or [dev environments](../../docs/dev-environments.md), leveraging
volumes can significantly streamline your workflow and improve overall performance.