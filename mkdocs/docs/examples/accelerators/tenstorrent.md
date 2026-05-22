---
title: Tenstorrent
description: Running dev environments, tasks, and services on Tenstorrent accelerators
---

# Tenstorrent

`dstack` supports running dev environments, tasks, and services on Tenstorrent
accelerators via SSH fleets.


??? info "SSH fleets"
    <div editor-title="tt-fleet.dstack.yml"> 

    ```yaml
    type: fleet
    name: tt-fleet

    ssh_config:
      user: root
      identity_file: ~/.ssh/id_rsa
      # Configure any number of Tenstorrent hosts, e.g. Galaxy systems
      hosts:
        - 192.168.2.108
    ```

    </div>

    > Hosts should be pre-installed with [Tenstorrent software](https://docs.tenstorrent.com/getting-started/README.html#software-installation).
    This should include the drivers, `tt-smi`, and HugePages.

    To apply the fleet configuration, run:

    <div class="termy">

    ```bash
    $ dstack apply -f tt-fleet.dstack.yml

     FLEET     RESOURCES                                                          PRICE  STATUS  CREATED
     tt-fleet  cpu=64 mem=566.1GB disk=749.6GB gpu=tt-galaxy-wh:12GB:32           $0     idle    18 sec ago
    ```

    </div>

    For more details on fleet configuration, refer to [SSH fleets](../../concepts/fleets.md#ssh-fleets).

## Services

Here's an example of a service that deploys
[`gpt-oss-120b`](https://huggingface.co/openai/gpt-oss-120b) on a
Tenstorrent Galaxy system using
[Tenstorrent Inference Server](https://github.com/tenstorrent/tt-inference-server).

<div editor-title="service.dstack.yml"> 

```yaml
type: service
name: gpt-oss-120b

image: ghcr.io/tenstorrent/tt-inference-server/vllm-tt-metal-src-release-ubuntu-22.04-amd64:0.12.0-805f43d-a45c614

env:
  - HF_TOKEN

commands:
  - | 
    ulimit -n 65535
    /home/container_app_user/tt-metal/python_env/bin/python /home/container_app_user/app/src/run_vllm_api_server.py \
      --model gpt-oss-120b \
      --tt-device galaxy

port: 8000

model: openai/gpt-oss-120b

volumes:
  # Cache model weights and TT runtime artifacts on the host.
  - /mnt/data/gpt-oss-120b/cache_root:/home/container_app_user/cache_root
  - /mnt/data/gpt-oss-120b/dot-cache:/home/container_app_user/.cache

resources:
  shm_size: 32GB
  gpu: tt-galaxy-wh:32
```

</div>

Go ahead and run the configuration using `dstack apply`:

<div class="termy">

```bash
$ export HF_TOKEN=<your-hf-token>
$ dstack apply -f service.dstack.yml
```

</div>

Once the service is up, it will be available via the service endpoint
at `<dstack server URL>/proxy/services/<project name>/<run name>/`.

<div class="termy">

```shell
$ curl http://127.0.0.1:3000/proxy/services/main/gpt-oss-120b/v1/chat/completions \
    -X POST \
    -H 'Authorization: Bearer &lt;user token&gt;' \
    -H 'Content-Type: application/json' \
    -d '{
      "model": "openai/gpt-oss-120b",
      "messages": [
        {
          "role": "user",
          "content": "What is 17 + 25? Answer with just the number."
        }
      ],
      "max_tokens": 128
    }'
```

</div>

The response includes both the final answer and the model's reasoning fields
(`reasoning` and `reasoning_content`).

Additionally, the model is available via `dstack`'s control plane UI:

![](https://dstack.ai/static-assets/static-assets/images/dstack-tenstorrent-model-ui.png){ width=800 }

When a [gateway](../../concepts/gateways.md) is configured, the service endpoint 
is available at `https://<run name>.<gateway domain>/`.

> Services support many options, including authentication, auto-scaling policies, etc. To learn more, refer to [Services](../../concepts/services.md).

## Tasks

Below is a task that simply runs `tt-smi -s`. Tasks can be used for training, fine-tuning, batch inference, or anything else.

<div editor-title="tt-task.dstack.yml"> 

```yaml
type: task
# The name is optional, if not specified, generated randomly
name: tt-smi

env:
  - HF_TOKEN

# (Required) Use any image with TT drivers 
image: dstackai/tt-smi:latest

# Use any commands
commands:
  - tt-smi -s

# Specify the number of accelerators, model, etc
resources:
  gpu: tt-galaxy-wh:32

# Uncomment if you want to run on a cluster of nodes
#nodes: 2
```

</div>

> Tasks support many options, including multi-node configuration, max duration, etc. To learn more, refer to [Tasks](../../concepts/tasks.md).

## Dev environments

Below is an example of a dev environment configuration. It can be used to provision a dev environment that can be accessed via your desktop IDE.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode

# (Optional) List required env variables
env:
  - HF_TOKEN

image: dstackai/tt-smi:latest

# Can be `vscode` or `cursor`
ide: vscode

resources:
  gpu: tt-galaxy-wh:32
```

</div>

If you run it via `dstack apply`, it will output the URL to access it via your desktop IDE.

![](https://dstack.ai/static-assets/static-assets/images/dstack-tenstorrent-vscode.png){ width=800 }

> Dev environments support many options, including inactivity and max duration, IDE configuration, etc. To learn more, refer to [Dev environments](../../concepts/tasks.md).

## GPU specification

`resources.gpu` uses the usual `name:count` format. For Tenstorrent, `count`
is the number of devices reported from the TT-SMI topology. On Galaxy systems,
this corresponds to chips. On PCIe systems, this is usually the card count, but
dual-chip cards can also be reported as per-chip devices.

```yaml
resources:
  gpu: tt-galaxy-wh:32  # Galaxy Wormhole, 32 chips
  # gpu: tt-galaxy-bh:32  # Galaxy Blackhole, 32 chips
  # gpu: n300:4           # TT-LoudBox or TT-QuietBox Wormhole, 4 n300 cards
  # gpu: p150:4           # TT-QuietBox Blackhole, 4 p150 cards
  # gpu: p300:64GB:2      # TT-QuietBox 2 Blackhole, 2 p300 cards
  # gpu: p300:32GB:4      # TT-QuietBox 2 Blackhole, if exposed per chip
```

Use `tt:<count>` only when the workload can run on any Tenstorrent device type.
Use a model name when placement depends on the hardware family: `n150` or
`n300` for Wormhole PCIe cards, `tt-galaxy-wh` for Galaxy Wormhole, `p100a`,
`p150`, or `p300` for Blackhole PCIe cards, and `tt-galaxy-bh` for Galaxy
Blackhole.

??? info "Feedback"
    Found a bug, or want to request a feature? File it in the [issue tracker](https://github.com/dstackai/dstack/issues),
    or share via [Discord](https://discord.gg/u8SmfwPpMd).
