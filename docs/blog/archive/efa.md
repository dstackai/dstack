---
title: Efficient distributed training with AWS EFA
date: 2025-02-20
description: "The latest release of dstack allows you to use AWS EFA for your distributed training tasks."  
slug: efa
image: https://dstack.ai/static-assets/static-assets/images/distributed-training-with-aws-efa-v2.png
categories:
  - Cloud fleets
---

# Efficient distributed training with AWS EFA

[Amazon Elastic Fabric Adapter (EFA) :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"} is a high-performance network interface designed for AWS EC2 instances, enabling
ultra-low latency and high-throughput communication between nodes. This makes it an ideal solution for scaling
distributed training workloads across multiple GPUs and instances.

With the latest release of `dstack`, you can now leverage AWS EFA to supercharge your distributed training tasks.

<img src="https://dstack.ai/static-assets/static-assets/images/distributed-training-with-aws-efa-v2.png" width="630"/>

<!-- more -->

## About EFA

AWS EFA delivers up to 400 Gbps of bandwidth, enabling lightning-fast GPU-to-GPU communication across nodes. By
bypassing the kernel and providing direct network access, EFA minimizes latency and maximizes throughput. Its native
integration with the `nccl` library ensures optimal performance for large-scale distributed training.

With EFA, you can scale your training tasks to thousands of nodes.

To use AWS EFA with `dstack`, follow these steps to run your distributed training tasks.

## Configure the backend

Before using EFA, ensure the `aws` backend is properly configured.

If you're using P4 or P5 instances with multiple
network interfaces, you’ll need to disable public IPs. Note, the `dstack`
server in this case should have access to the private subnet of the VPC.

You’ll also need to specify an AMI that includes the GDRCopy drivers. For example, you can use the 
[AWS Deep Learning Base GPU AMI :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/releasenotes/aws-deep-learning-base-gpu-ami-ubuntu-22-04/){:target="_blank"}.

Here’s an example backend configuration:

<server/.dstack/config.yml example>

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
      vpc_name: my-vpc
      os_images:
        nvidia:
          name: Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04) 20241115
          owner: 898082745236
          user: ubuntu
```

</div>

## Create a fleet

Once the backend is configured, you can create a fleet for distributed training. Here’s an example fleet
configuration:

<div editor-title="examples/misc/fleets/efa.dstack.yml">
    
    ```yaml
    type: fleet
    name: my-efa-fleet
    
    # Specify the number of instances
    nodes: 2
    placement: cluster
    
    resources:
      gpu: H100:8
    ```
    
</div>

To provision the fleet, use the [`dstack apply`](../../docs/reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f examples/misc/efa/fleet.dstack.yml

Provisioning...
---> 100%

 FLEET         INSTANCE  BACKEND          GPU          PRICE   STATUS  CREATED 
 my-efa-fleet  0         aws (us-west-2)  8xH100:80GB  $98.32  idle    3 mins ago      
               1         aws (us-west-2)  8xH100:80GB  $98.32  idle    3 mins ago    
```

</div>

## Submit the task

With the fleet provisioned, you can now submit your distributed training task. Here’s an example task configuration:

<div editor-title="examples/misc/efa/task.dstack.yml">

```yaml
type: task
name: efa-task

# The size of the cluster
nodes: 2

python: 3.12

# Commands to run on each node
commands:
  - pip install requirements.txt
  - accelerate launch
    --num_processes $DSTACK_NODES_NUM
    --num_machines $DSTACK_NODES_NUM
    --machine_rank $DSTACK_NODE_RANK
    --main_process_ip $DSTACK_MASTER_NODE_IP
    --main_process_port 29500
    task.py

env:
  - LD_LIBRARY_PATH=/opt/nccl/build/lib:/usr/local/cuda/lib64:/opt/amazon/efa/lib:/opt/amazon/openmpi/lib:/opt/aws-ofi-nccl/lib:$LD_LIBRARY_PATH
  - FI_PROVIDER=efa
  - FI_EFA_USE_HUGE_PAGE=0
  - OMPI_MCA_pml=^cm,ucx
  - NCCL_TOPO_FILE=/opt/amazon/efa/share/aws-ofi-nccl/xml/p4d-24xl-topo.xml  # Typically loaded automatically, might not be necessary
  - OPAL_PREFIX=/opt/amazon/openmpi
  - NCCL_SOCKET_IFNAME=^docker0,lo
  - FI_EFA_USE_DEVICE_RDMA=1
  - NCCL_DEBUG=INFO  # Optional debugging for NCCL communication
  - NCCL_DEBUG_SUBSYS=TUNING

resources:
  gpu: H100:8
  shm_size: 24GB
```

</div>

Submit the task using the [`dstack apply`](../../docs/reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f examples/misc/efa/task.dstack.yml -R
```

</div>

`dstack` will automatically run the container on each node of the cluster, passing the necessary environment variables.
`nccl` will leverage the EFA drivers and the specified environment variables to enable high-performance communication via
EFA.

> Have questions? You're welcome to join
> our [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"} or talk
> directly to [our team :material-arrow-top-right-thin:{ .external }](https://calendly.com/dstackai/discovery-call){:target="_blank"}.

!!! info "What's next?"
    1. Check [fleets](../../docs/concepts/fleets.md), [tasks](../../docs/concepts/tasks.md), and [volumes](../../docs/concepts/volumes.md)
    2. Also see [dev environments](../../docs/concepts/dev-environments.md) and [services](../../docs/concepts/services.md)
    3. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
