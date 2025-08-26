# Wan2.2

[Wan2.2](https://github.com/Wan-Video/Wan2.2) is an open-source SOTA foundational video model. This example shows how to run the T2V-A14B model variant via `dstack` for text-to-video generation.

??? info "Prerequisites"
    Once `dstack` is [installed](https://dstack.ai/docs/installation), clone the repo with examples.

    <div class="termy">
 
    ```shell
    $ git clone https://github.com/dstackai/dstack
    $ cd dstack
    ```
 
    </div>

Apply the [configuration](https://github.com/dstackai/dstack/blob/master/examples/models/wan22/dev-env.dstack.yml) to provision a GPU instance and run a dev environment with all the Wan2.2 dependencies installed:

<div class="termy">

```shell
$ dstack apply -f examples/models/wan22/dev-env.dstack.yml
Provisioning...
---> 100%
```

</div>

Then you can attach to the dev environment and generate videos:

<div class="termy">

```shell
$ torchrun --nproc_per_node=8 generate.py --task t2v-A14B --size 1280*720 --ckpt_dir ./Wan2.2-T2V-A14B --dit_fsdp --t5_fsdp --ulysses_size 8 --prompt "Two anthropomorphic cats in comfy boxing gear and bright gloves fight intensely on a spotlighted stage."

[2025-08-26 05:41:54,911] INFO: Input prompt: Two anthropomorphic cats in comfy boxing gear and bright gloves fight intensely on a spotlighted stage.
[2025-08-26 05:41:54,912] INFO: Creating WanT2V pipeline.
[2025-08-26 05:42:50,296] INFO: loading ./Wan2.2-T2V-A14B/models_t5_umt5-xxl-enc-bf16.pth
```

</div>
