# AWS EFA

In this guide, we’ll walk through how to run high-performance distributed training on AWS using [Amazon Elastic Fabric Adapter (EFA) :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"} with `dstack`.

## Overview

EFA is a network interface for Amazon EC2 that enables low-latency, high-bandwidth inter-node communication — essential for scaling distributed deep learning. With `dstack`, EFA is automatically enabled when you create fleets with supported instance types.

## Prerequisite

Before you start, make sure the `aws` backend is properly configured.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: aws
      creds:
        type: default
      regions: ["us-west-2"]

      public_ips: false
      vpc_name: my-custom-vpc
```

</div>

!!! info "Multiple network interfaces"
    To use P4, P5, or P6 instances, set `public_ips` to `false` — this allows AWS to attach multiple network interfaces for EFA. In this case, the `dstack` server can reach your VPC’s private subnets.

!!! info "VPC"
    If you use a custom VPC, verify that it permits all internal traffic between nodes for EFA to function properly

## Create a fleet

Once your backend is ready, define a fleet configuration.

<div editor-title="examples/clusters/efa/fleet.dstack.yml">
    
    ```yaml
    type: fleet
    name: my-efa-fleet
    
    nodes: 2
    placement: cluster
    
    resources:
      gpu: H100:8
    ```
    
</div>

Provision the fleet with `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f examples/clusters/efa/fleet.dstack.yml

Provisioning...
---> 100%

 FLEET         INSTANCE  BACKEND          INSTANCE TYPE  GPU          PRICE   STATUS  CREATED 
 my-efa-fleet  0         aws (us-west-2)  p4d.24xlarge   H100:8:80GB  $98.32  idle    3 mins ago      
               1         aws (us-west-2)  p4d.24xlarge   $98.32  idle    3 mins ago    
```

</div>

??? info "Instance types"
    `dstack` selects suitable instances automatically, but not
    [all types support EFA :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}.
    To enforce EFA, you can specify `instance_types` explicitly:

    ```yaml
    type: fleet
    name: my-efa-fleet
    
    nodes: 2
    placement: cluster
    
    resources:
      gpu: L4

    instance_types: ["g6.8xlarge"] # If not specified, g6.xlarge is used (won't have EFA)
    ```
      
## Run NCCL tests

To confirm that EFA is working, run NCCL tests:

<div editor-title="examples/clusters/nccl-tests/.dstack.yml">

```yaml
type: task
name: nccl-tests

nodes: 2

startup_order: workers-first
stop_criteria: master-done

env:
  - NCCL_DEBUG=INFO
commands:
  - |
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      mpirun \
        --allow-run-as-root \
        --hostfile $DSTACK_MPI_HOSTFILE \
        -n $DSTACK_GPUS_NUM \
        -N $DSTACK_GPUS_PER_NODE \
        --bind-to none \
        /opt/nccl-tests/build/all_reduce_perf -b 8 -e 8G -f 2 -g 1
    else
      sleep infinity
    fi

resources:
  gpu: 1..8
  shm_size: 16GB
```

</div>

Run it with `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f examples/clusters/nccl-tests/.dstack.yml

Provisioning...
---> 100%
```

</div>

!!! info "Docker image"
    You can use your own container by setting `image`. If omitted, `dstack` uses its default image with drivers, NCCL tests, and tools pre-installed.

## Run distributed training

Here’s an example using `torchrun` for a simple multi-node PyTorch job:

<div editor-title="examples/distributed-training/torchrun/.dstack.yml">

```yaml
type: task
name: train-distrib

nodes: 2

python: 3.12
env:
  - NCCL_DEBUG=INFO
commands:
  - git clone https://github.com/pytorch/examples.git pytorch-examples
  - cd pytorch-examples/distributed/ddp-tutorial-series
  - uv pip install -r requirements.txt
  - |
    torchrun \
      --nproc-per-node=$DSTACK_GPUS_PER_NODE \
      --node-rank=$DSTACK_NODE_RANK \
      --nnodes=$DSTACK_NODES_NUM \
      --master-addr=$DSTACK_MASTER_NODE_IP \
      --master-port=12345 \
      multinode.py 50 10

resources:
  gpu: 1..8
  shm_size: 16GB
```

</div>

Provision and launch it via `dstack apply`.

<div class="termy">

```shell
$ dstack apply -f examples/distributed-training/torchrun/.dstack.yml

Provisioning...
---> 100%
```

</div>

Instead of setting `python`, you can specify your own Docker image using `image`. Make sure that the image is properly configured for EFA.

!!! info "What's next"
    1. Learn more about [distributed tasks](https://dstack.ai/docs/concepts/tasks#distributed-tasks) 
    2. Check [dev environments](https://dstack.ai/docs/concepts/dev-environments),
       [services](https://dstack.ai/docs/concepts/services), and [fleets](https://dstack.ai/docs/concepts/fleets)
    3. Read the [Clusters](https://dstack.ai/docs/guides/clusters) guide
