# Wan2.2

[Wan2.2 :material-arrow-top-right-thin:{ .external }](https://github.com/Wan-Video/Wan2.2){:target="_blank"} is an open-source SOTA foundational video model. This example shows how to run the T2V-A14B model variant via `dstack` for text-to-video generation.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

## Define a configuration

Below is a task configuration that generates a video using Wan2.2, uploads it, and provides the download link.

<div editor-title="examples/models/wan22/.dstack.yml"> 

```yaml
type: task
name: wan22

repos:
  # Clones it to `/workflow` (the default working directory)
  - https://github.com/Wan-Video/Wan2.2.git

python: 3.12
nvcc: true

env:
  - PROMPT="Two anthropomorphic cats in comfy boxing gear and bright gloves fight intensely on a spotlighted stage."
  # Required for storing cache on a volume
  - UV_LINK_MODE=copy
commands:
  # Install flash-attn
  - |
    uv pip install torch
    uv pip install flash-attn --no-build-isolation 
  # Install dependencies
  - |
    uv pip install . decord librosa
    uv pip install "huggingface_hub[cli]"
    hf download Wan-AI/Wan2.2-T2V-A14B --local-dir /root/.cache/Wan2.2-T2V-A14B
  # Generate video
  - |
    if [ ${DSTACK_GPUS_NUM} -gt 1 ]; then
      torchrun \
        --nproc_per_node=${DSTACK_GPUS_NUM} \
        generate.py \
        --task t2v-A14B \
        --size 1280*720 \
        --ckpt_dir /root/.cache/Wan2.2-T2V-A14B \
        --dit_fsdp --t5_fsdp --ulysses_size ${DSTACK_GPUS_NUM} \
        --save_file ${DSTACK_RUN_NAME}.mp4 \
        --prompt "${PROMPT}"
    else
      python generate.py \
        --task t2v-A14B \
        --size 1280*720 \
        --ckpt_dir /root/.cache/Wan2.2-T2V-A14B \
        --offload_model True \
        --convert_model_dtype \
        --save_file ${DSTACK_RUN_NAME}.mp4 \
        --prompt "${PROMPT}"
    fi
  # Upload video
  - curl https://bashupload.com/ -T ./${DSTACK_RUN_NAME}.mp4

resources: 
  gpu:
    name: [H100, H200]
    count: 1..8
  disk: 300GB

# Change to on-demand for disabling spot
spot_policy: auto

volumes:
  # Cache pip packages and HF models
  - instance_path: /root/dstack-cache
    path: /root/.cache/
    optional: true
```

</div>

You can customize the 

## Run the configuration

Once the configuration is ready, run `dstack apply -f <configuration file>`, and `dstack` will automatically provision the
cloud resources and run the configuration.

<div class="termy">

```shell
$ dstack apply -f examples/models/wan22/.dstack.yml

 #  BACKEND              RESOURCES                                        INSTANCE TYPE   PRICE
 1  datacrunch (FIN-01)  cpu=30 mem=120GB disk=200GB H100:80GB:1 (spot)   1H100.80S.30V   $0.99
 2  datacrunch (FIN-01)  cpu=30 mem=120GB disk=200GB H100:80GB:1 (spot)   1H100.80S.30V   $0.99
 3  datacrunch (FIN-02)  cpu=44 mem=182GB disk=200GB H200:141GB:1 (spot)  1H200.141S.44V  $0.99

---> 100%

Uploaded 1 file, 8 375 523 bytes

wget https://bashupload.com/fIo7l/wan22.mp4
```

</div>

If you want you can override the default GPU, spot policy, and even the prompt via the CLI.

<div class="termy">

```shell
$ PROMPT=...
$ dstack apply -f examples/models/wan22/.dstack.yml --spot --gpu H100,H200:8

 #  BACKEND              RESOURCES                                          INSTANCE TYPE    PRICE
 1  aws (us-east-2)      cpu=192 mem=2048GB disk=300GB H100:80GB:8 (spot)   p5.48xlarge      $6.963
 2  datacrunch (FIN-02)  cpu=176 mem=1480GB disk=300GB H100:80GB:8 (spot)   8H100.80S.176V   $7.93
 3  datacrunch (ICE-01)  cpu=176 mem=1450GB disk=300GB H200:141GB:8 (spot)  8H200.141S.176V  $7.96
 
---> 100%

Uploaded 1 file, 8 375 523 bytes

wget https://bashupload.com/fIo7l/wan22.mp4
```

</div>

## Source code

The source-code of this example can be found in
[`examples/models/wan22` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/models/wan22){:target="_blank"}.
