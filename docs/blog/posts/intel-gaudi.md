---
title: Supporting Intel Gaudi AI accelerators with SSH fleets
date: 2025-02-21
description: "dstack now supports Intel Gaudi accelerators with SSH fleets, simplifying container orchestration across private clouds and data centers."  
slug: intel-gaudi
image: https://dstack.ai/static-assets/static-assets/images/dstack-intel-gaudi-and-intel-tiber-cloud.png-v2
categories:
  - Changelog
---

# Supporting Intel Gaudi AI accelerators with SSH fleets

At `dstack`, our goal is to make AI container orchestration simpler and fully vendor-agnostic. That’s why we support not
just leading cloud providers and on-prem environments but also a wide range of accelerators.

With our latest release, we’re adding support
for Intel Gaudi AI Accelerator and launching a new partnership with Intel.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-intel-gaudi-and-intel-tiber-cloud-v2.png" width="630"/>

<!-- more -->

## About Intel Gaudi

Intel Gaudi AI Accelerator is a series of accelerators built to handle AI tasks. Powered by Intel’s Habana architecture, Gaudi is
tailored for high-performance AI inference and training, offering high throughput and efficiency. It has a scalable
design with numerous cores and ample memory bandwidth, enabling better performance per watt.

Here's a brief spec for Gaudi 2 and Gaudi 3:

|                      | **Gaudi 2** | **Gaudi 3** |
|----------------------|-------------|-------------|
| **MME Units**        | 2           | 8           |
| **TPC Units**        | 24          | 64          |
| **HBM Capacity**     | 96 GB       | 128 GB      |
| **HBM Bandwidth**    | 2.46 TB/s   | 3.7 TB/s    |
| **Networking**       | 600 GB/s    | 1200 GB/s   |
| **FP8 Performance**  | 865 TFLOPs  | 1835 TFLOPs |
| **BF16 Performance** | 432 TFLOPs  | 1835 TFLOPs |

In the latest release, `dstack` now supports the orchestration of containers across on-prem 
machines equipped with Intel Gaudi accelerators.

## Create a fleet

To manage container workloads on on-prem machines with Intel Gaudi accelerators, start by configuring an 
[SSH fleet](../../docs/concepts/fleets.md#ssh). Here’s an example configuration for your fleet:

<div editor-title="examples/misc/fleets/gaudi.dstack.yml">

```yaml
type: fleet
name: my-gaudi2-fleet
ssh_config:
  hosts:
    - hostname: 100.83.163.67
      user: sdp
      identity_file: ~/.ssh/id_rsa
      blocks: auto
    - hostname: 100.83.163.68
      user: sdp
      identity_file: ~/.ssh/id_rsa
      blocks: auto
  proxy_jump:
    hostname: 146.152.186.135
    user: guest
    identity_file: ~/.ssh/intel_id_rsa
```

</div>

To provision the fleet, run the [`dstack apply`](../../docs/reference/cli/dstack/apply.md) command:

<div class="termy">

```shell
$ dstack apply -f examples/misc/fleets/gaudi.dstack.yml

Provisioning...
---> 100%

 FLEET            INSTANCE  BACKEND  GPU                        STATUS  CREATED 
 my-gaudi2-fleet  0         ssh      152xCPU, 1007GB, 8xGaudi2  idle    3 mins ago
                                     (96GB), 388.0GB (disk)     
                  1         ssh      152xCPU, 1007GB, 8xGaudi2  idle    3 mins ago
                                     (96GB), 388.0GB (disk)     
```

</div>

## Apply a configuration

With your fleet provisioned, you can now run [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md). 

Below is an example of a task configuration for fine-tuning the [`DeepSeek-R1-Distill-Qwen-7B` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B){:target="_blank"}
model using [Optimum for Intel Gaudi :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-habana){:target="_blank"} 
and [DeepSpeed :material-arrow-top-right-thin:{ .external }](https://docs.habana.ai/en/latest/PyTorch/DeepSpeed/DeepSpeed_User_Guide/DeepSpeed_User_Guide.html#deepspeed-user-guide){:target="_blank"} with 
the [`lvwerra/stack-exchange-paired` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/lvwerra/stack-exchange-paired){:target="_blank"} dataset:

<div editor-title="examples/single-node-training/trl/intel/.dstack.yml">
    
```yaml
type: task
name: trl-train

image: vault.habana.ai/gaudi-docker/1.18.0/ubuntu22.04/habanalabs/pytorch-installer-2.4.0
env:
  - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
  - WANDB_API_KEY
  - WANDB_PROJECT
commands:
   - pip install --upgrade-strategy eager optimum[habana]
   - pip install git+https://github.com/HabanaAI/DeepSpeed.git@1.19.0
   - git clone https://github.com/huggingface/optimum-habana.git
   - cd optimum-habana/examples/trl
   - pip install -r requirements.txt
   - pip install wandb
   - DEEPSPEED_HPU_ZERO3_SYNC_MARK_STEP_REQUIRED=1 python ../gaudi_spawn.py --world_size $DSTACK_GPUS_NUM --use_deepspeed sft.py
       --model_name_or_path $MODEL_ID
       --dataset_name "lvwerra/stack-exchange-paired"
       --deepspeed ../language-modeling/llama2_ds_zero3_config.json
       --output_dir="./sft"
       --do_train
       --max_steps=500
       --logging_steps=10
       --save_steps=100
       --per_device_train_batch_size=1
       --per_device_eval_batch_size=1
       --gradient_accumulation_steps=2
       --learning_rate=1e-4
       --lr_scheduler_type="cosine"
       --warmup_steps=100
       --weight_decay=0.05
       --optim="paged_adamw_32bit"
       --lora_target_modules "q_proj" "v_proj"
       --bf16
       --remove_unused_columns=False
       --run_name="sft_deepseek_70"
       --report_to="wandb"
       --use_habana
       --use_lazy_mode

resources:
  gpu: gaudi2:8
```    

</div>

Submit the task using the [`dstack apply`](../../docs/reference/cli/dstack/apply.md) command:

<div class="termy">

```shell
$ dstack apply -f examples/single-node-training/trl/intel/.dstack.yml -R
```

</div>

`dstack` will automatically create containers according to the run configuration and execute them across the fleet.

> Explore our [examples](../../examples/accelerators/intel/index.md) to learn how to train and deploy large models on
> Intel Gaudi AI Accelerator.

!!! info "Intel Tiber AI Cloud"
    At `dstack`, we’re grateful to be part of the Intel Liftoff program, which allowed us to access Intel Gaudi AI
    accelerators via [Intel Tiber AI Cloud :material-arrow-top-right-thin:{ .external }](https://www.intel.com/content/www/us/en/developer/tools/tiber/ai-cloud.html){:target="_blank"}.
    You can sign up if you’d like to access Intel Gaudi AI accelerators via the cloud.

    Native integration with Intel Tiber AI Cloud is also coming soon to `dstack`.

!!! info "What's next?"
    1. Refer to [Quickstart](../../docs/quickstart.md)
    2. Check [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), and [fleets](../../docs/concepts/fleets.md)
    3. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
