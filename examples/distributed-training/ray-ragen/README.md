# Ray + RAGEN

This example shows how use `dstack` and [RAGEN :material-arrow-top-right-thin:{ .external }](https://github.com/RAGEN-AI/RAGEN){:target="_blank"} 
to fine-tune an agent on mulitiple nodes.

Under the hood `RAGEN` uses [verl :material-arrow-top-right-thin:{ .external }](https://github.com/volcengine/verl){:target="_blank"} for Reinforcement Learning and [Ray :material-arrow-top-right-thin:{ .external }](https://docs.ray.io/en/latest/){:target="_blank"} for ditributed training.

## Create fleet

Before submitted disributed training runs, make sure to create a fleet with a `placement` set to `cluster`.

> For more detials on how to use clusters with `dstack`, check the [Clusters](https://dstack.ai/docs/guides/clusters) guide.

## Run a Ray cluster

If you want to use Ray with `dstack`, you have to first run a Ray cluster.

The task below runs a Ray cluster on an existing fleet:

<div editor-title="examples/distributed-training/ray-ragen/.dstack.yml">

```yaml
type: task
name: ray-ragen-cluster

nodes: 2

env:
- WANDB_API_KEY
image: whatcanyousee/verl:ngc-cu124-vllm0.8.5-sglang0.4.6-mcore0.12.0-te2.2
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
  - |
    if [ $DSTACK_NODE_RANK = 0 ]; then 
        ray start --head --port=6379;
    else
        ray start --address=$DSTACK_MASTER_NODE_IP:6379
    fi

# Expose Ray dashboard port
ports:
  - 8265

resources:
  gpu: 80GB:8
  shm_size: 128GB

# Save checkpoints on the instance
volumes:
  - /checkpoints:/checkpoints
```

</div>

We are using verl's docker image for vLLM with FSDP. See [Installation :material-arrow-top-right-thin:{ .external }](https://verl.readthedocs.io/en/latest/start/install.html){:target="_blank"} for more.

The `RAGEN` setup script `scripts/setup_ragen.sh` isolates dependencies within Conda environment.

Note that the Ray setup in the RAGEN environment is missing the dashboard, so we reinstall it using `ray[default]`.

Now, if you run this task via `dstack apply`, it will automatically forward the Ray's dashboard port to `localhost:8265`.

<div class="termy">

```shell
$ dstack apply -f examples/distributed-training/ray-ragen/.dstack.yml
```

</div>

As long as the `dstack apply` is attached, you can use `localhost:8265` to submit Ray jobs for execution.
If `dstack apply` is detached, you can use `dstack attach` to re-attach.

## Submit Ray jobs

Before you can submit Ray jobs, ensure to install `ray` locally:

<div class="termy">

```shell
$ pip install ray
```

</div>

Now you can submit the training job to the Ray cluster which is available at `localhost:8265`:

<div class="termy">

```shell
$ RAY_ADDRESS=http://localhost:8265
$ ray job submit \
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

</div>

!!! info "Training parameters"
    1. `actor_rollout_ref.rollout.tensor_model_parallel_size=4`, because `Qwen/Qwen2.5-7B-Instruct` has 28 attention heads and number of attention heads should be divisible by `tensor_model_parallel_size`
    2. `actor_rollout_ref.rollout.tp_size_check=False`, if True `tensor_model_parallel_size` should be equal to `trainer.n_gpus_per_node`
    3. `micro_batch_size_per_gpu=2`, to keep the RAGEN-paper's `rollout_filter_ratio` and `es_manager` settings as it is for world size `16`

Using Ray via `dstack` is a powerful way to get access to the rich Ray ecosystem while benefiting from `dstack`'s provisioning capabilities.

!!! info "What's next"
    1. Check the [Clusters](https://dstack.ai/docs/guides/clusters) guide
    2. Read about [distributed tasks](https://dstack.ai/docs/concepts/tasks#distributed-tasks) and [fleets](https://dstack.ai/docs/concepts/fleets)
    3. Browse Ray's [docs :material-arrow-top-right-thin:{ .external }](https://docs.ray.io/en/latest/train/examples.html){:target="_blank"} for other examples.
