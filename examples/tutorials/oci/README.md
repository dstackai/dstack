## Run fine-tuning

```console
$ ACCEL_CONFIG_PATH=fsdp_qlora_full_shard.yaml \   
    FT_MODEL_CONFIG_PATH=qlora_finetune_config.yaml \
    HUGGING_FACE_HUB_TOKEN=xxxx \
    WANDB_API_KEY=xxxx \
    dstack run . -f ft.task.dstack.yml -d
```

## Run TGI backed serving

```console
$ HUGGING_FACE_HUB_TOKEN=xxxx \
    dstack run . -f serve.service.dstack.yml -d
```