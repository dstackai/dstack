# Agent Fine Tuning

This example shows how use `dstack` and [RAGEN](https://github.com/RAGEN-AI/RAGEN) for multi-node Agent Fine Tuning. Under the hood `RAGEN` uses [VERL](https://github.com/volcengine/verl) for Reinforcement Learning.

## Create fleet

Create an SSH fleet through the login node specified via [proxy_jump](https://dstack.ai/blog/gpu-blocks-and-proxy-jump/#proxy-jump).

```yaml
type: fleet
name: lambda-h100-fleet

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/peterschmidt85
  hosts:
    - lambda-cluster-node-001
    - lambda-cluster-node-002
  proxy_jump:
    hostname: 192.222.48.90
    user: ubuntu
    identity_file: ~/.ssh/id_rsa

placement: cluster
```

```shell
dstack apply -f lambda-h100-fleet.yaml
```

## Launch Ray cluster

The following `dstack` task sets up `RAGEN` and launches Ray master and worker nodes.
`dstack` makes the Ray dashboard available at `localhost:8265`.

```yaml
type: task
name: agent-fine-tuning
nodes: 2
image: whatcanyousee/verl:ngc-cu124-vllm0.8.5-sglang0.4.6-mcore0.12.0-te2.2

env:
- WANDB_API_KEY

commands:
  - wget -O miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
  - bash miniconda.sh -b -p /workflow/miniconda
  - eval "$(/workflow/miniconda/bin/conda shell.bash hook)"
  - git clone https://github.com/RAGEN-AI/RAGEN.git
  - cd RAGEN
  - bash scripts/setup_ragen.sh
  - conda activate ragen
  - cd verl
  - pip install --no-deps -e .
  - pip install hf_transfer hf_xet
  - pip uninstall -y ray
  - pip install -U "ray[default]"
  - >
    if [ $DSTACK_NODE_RANK = 0 ]; then 
        ray start --head --port=6379;
    else
        ray start --address=$DSTACK_MASTER_NODE_IP:6379
    fi
ports:
  - 8265 # ray dashboard port
resources:
  gpu: nvidia:8:80GB 
  shm_size: 128GB

volumes:
  - /checkpoints:/checkpoints
```
!!! Note
    1. We are using `VERL` docker image for vLLM with FSDP. See [Installation](https://verl.readthedocs.io/en/latest/start/install.html)
    2.`RAGEN` setup script `scripts/setup_ragen.sh` isolates dependencies within Conda environment. 
    3. The Ray setup in the RAGEN environment is missing the dashboard, so we reinstall it using "ray[default]".

```shell
dstack apply -f agent-fine-tuning.yaml
```

## Run Ray jobs

Install Ray locally:

```shell
pip install ray
```

Now you can submit agent fine tuning job to the cluster available at `localhost:8265`:

```shell
RAY_ADDRESS='http://localhost:8265' \
ray job submit \
-- bash -c "\
  export PYTHONPATH=/workflow/RAGEN; \
  cd /workflow/RAGEN; \
  /workflow/miniconda/envs/ragen/bin/python train.py \
    --config-name base \
    system.CUDA_VISIBLE_DEVICES=[0,1,2,3,4,5,6,7] \
    model_path=Qwen/Qwen2.5-7B-Instruct \
    trainer.experiment_name=agent-fine-tuning-Qwen2.5-7B \
    trainer.n_gpus_per_node=8 \
    trainer.nnodes=2 \
    micro_batch_size_per_gpu=2 \
    trainer.default_local_dir=/checkpoints \
    trainer.save_freq=50 \
    actor_rollout_ref.rollout.tp_size_check=False \
    actor_rollout_ref.rollout.tensor_model_parallel_size=4"
```

!!! info "Training Parameters"
    1. `actor_rollout_ref.rollout.tensor_model_parallel_size=4`, because Qwen/Qwen2.5-7B-Instruct has 28 attention heads and number of attention heads should be divisible by `tensor_model_parallel_size`. 
    2. `actor_rollout_ref.rollout.tp_size_check=False`, if True `tensor_model_parallel_size` should be equal to `trainer.n_gpus_per_node`
    3. `micro_batch_size_per_gpu=2`, to keep the RAGEN-paper's `rollout_filter_ratio` and `es_manager` settings as it is for world size `16`.

See more examples in the [Ray docs](https://docs.ray.io/en/latest/train/examples.html).

Using Ray via `dstack` is a powerful way to get access to the rich Ray ecosystem while benefiting from `dstack`'s provisioning capabilities.
