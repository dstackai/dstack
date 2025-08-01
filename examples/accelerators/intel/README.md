# Intel Gaudi

`dstack` supports running dev environments, tasks, and services on Intel Gaudi GPUs via 
[SSH fleets](https://dstack.ai/docs/concepts/fleets#ssh).

## Deployment

Serving frameworks like vLLM and TGI have Intel Gaudi support. Here's an example of
a service that deploys
[`DeepSeek-R1-Distill-Llama-70B` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Llama-70B){:target="_blank"} 
using [TGI on Gaudi :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/tgi-gaudi){:target="_blank"} 
and [vLLM :material-arrow-top-right-thin:{ .external }](https://github.com/HabanaAI/vllm-fork){:target="_blank"}.

=== "TGI"
    <div editor-title="examples/inference/tgi/intel/.dstack.yml"> 
    
    ```yaml
    type: service
    name: tgi

    image: ghcr.io/huggingface/tgi-gaudi:2.3.1
    env:
    - HF_TOKEN
    - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-70B
    - PORT=8000
    - OMPI_MCA_btl_vader_single_copy_mechanism=none
    - TEXT_GENERATION_SERVER_IGNORE_EOS_TOKEN=true
    - PT_HPU_ENABLE_LAZY_COLLECTIVES=true
    - MAX_TOTAL_TOKENS=2048
    - BATCH_BUCKET_SIZE=256
    - PREFILL_BATCH_BUCKET_SIZE=4
    - PAD_SEQUENCE_TO_MULTIPLE_OF=64
    - ENABLE_HPU_GRAPH=true
    - LIMIT_HPU_GRAPH=true
    - USE_FLASH_ATTENTION=true
    - FLASH_ATTENTION_RECOMPUTE=true
    commands:
      - text-generation-launcher
        --sharded true
        --num-shard $DSTACK_GPUS_NUM
        --max-input-length 1024
        --max-total-tokens 2048
        --max-batch-prefill-tokens 4096
        --max-batch-total-tokens 524288
        --max-waiting-tokens 7
        --waiting-served-ratio 1.2
        --max-concurrent-requests 512
    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-70B

    resources:
      gpu: gaudi2:8

    # Uncomment to cache downloaded models
    #volumes:
    #  - /root/.cache/huggingface/hub:/root/.cache/huggingface/hub
    ```
    
    </div>

=== "vLLM"

    <div editor-title="examples/inference/vllm/intel/.dstack.yml"> 
    
    ```yaml
    type: service
    name: deepseek-r1-gaudi

    image: vault.habana.ai/gaudi-docker/1.19.0/ubuntu22.04/habanalabs/pytorch-installer-2.5.1:latest
    env:
    - MODEL_ID=deepseek-ai/DeepSeek-R1-Distill-Llama-70B
    - HABANA_VISIBLE_DEVICES=all
    - OMPI_MCA_btl_vader_single_copy_mechanism=none
    commands:
    - git clone https://github.com/HabanaAI/vllm-fork.git
    - cd vllm-fork
    - git checkout habana_main
    - pip install -r requirements-hpu.txt
    - python setup.py develop
    - vllm serve $MODEL_ID
        --tensor-parallel-size 8
        --trust-remote-code
        --download-dir /data
    port: 8000
    model: deepseek-ai/DeepSeek-R1-Distill-Llama-70B


    resources:
      gpu: gaudi2:8
    
    # Uncomment to cache downloaded models
    #volumes:
    #  - /root/.cache/huggingface/hub:/root/.cache/huggingface/hub
    ```
    </div>
    

## Fine-tuning

Below is an example of LoRA fine-tuning of [`DeepSeek-R1-Distill-Qwen-7B` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B){:target="_blank"}
using [Optimum for Intel Gaudi :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-habana){:target="_blank"} 
and [DeepSpeed :material-arrow-top-right-thin:{ .external }](https://docs.habana.ai/en/latest/PyTorch/DeepSpeed/DeepSpeed_User_Guide/DeepSpeed_User_Guide.html#deepspeed-user-guide){:target="_blank"} with 
the [`lvwerra/stack-exchange-paired` :material-arrow-top-right-thin:{ .external }](https://huggingface.co/datasets/lvwerra/stack-exchange-paired){:target="_blank"} dataset. 
    
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

To finetune `DeepSeek-R1-Distill-Llama-70B` with eight Gaudi 2, 
you can partially offload parameters to CPU memory using the Deepspeed configuration file.
For more details, refer to [parameter offloading](https://deepspeed.readthedocs.io/en/latest/zero3.html#deepspeedzerooffloadparamconfig).

## Applying a configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`.

<div class="termy">

```shell
$ dstack apply -f examples/inference/vllm/.dstack.yml

 #  BACKEND  REGION    RESOURCES                    SPOT  PRICE     
 1  ssh      remote    152xCPU,1007GB,8xGaudi2:96GB yes   $0     idle 

Submit a new run? [y/n]: y

Provisioning...
---> 100%
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/llms/deepseek/tgi/intel` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek/tgi/intel){:target="_blank"},
[`examples/llms/deepseek/vllm/intel` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek/vllm/intel){:target="_blank"} and
[`examples/llms/deepseek/trl/intel` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/llms/deepseek/trl/intel){:target="_blank"}.

!!! info "What's next?"
    1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), and [services](https://dstack.ai/docs/services).
    2. See also [Intel Gaudi Documentation :material-arrow-top-right-thin:{ .external }](https://docs.habana.ai/en/latest/index.html), [vLLM Inference with Gaudi](https://docs.habana.ai/en/latest/PyTorch/Inference_on_PyTorch/vLLM_Inference.html)
      and [Optimum for Gaudi examples :material-arrow-top-right-thin:{ .external }](https://github.com/huggingface/optimum-habana/blob/main/examples/trl/README.md).
