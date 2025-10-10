---
title: "Supporting MPI and NCCL/RCCL tests"
date: 2025-04-02
description: "TBA"
slug: mpi
image: https://dstack.ai/static-assets/static-assets/images/dstack-mpi-v2.png
categories:
  - Changelog
---

# Supporting MPI and NCCL/RCCL tests 

As AI models grow in complexity, efficient orchestration tools become increasingly important. 
[Fleets](../../docs/concepts/fleets.md) introduced by `dstack` last year streamline 
[task execution](../../docs/concepts/tasks.md) on both cloud and 
on-prem clusters, whether it's pre-training, fine-tuning, or batch processing.

The strength of `dstack` lies in its flexibility. Users can leverage distributed framework like
`torchrun`, `accelerate`, or others. `dstack` handles node provisioning, job execution, and automatically propagates
system environment variables—such as `DSTACK_NODE_RANK`, `DSTACK_MASTER_NODE_IP`,
`DSTACK_GPUS_PER_NODE` and [others](../../docs/concepts/tasks.md#system-environment-variables)—to containers.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-mpi-v2.png" width="630"/>

One use case `dstack` hasn’t supported until now is MPI, as it requires a scheduled environment or
direct SSH connections between containers. Since `mpirun` is essential for running NCCL/RCCL tests—crucial for large-scale
cluster usage—we’ve added support for it.

<!-- more -->

Below is an example of a task that runs AllReduce test on 2 nodes, each with 4 GPUs (8 processes in total).

<div editor-title="examples/distributed-training/nccl-tests/.dstack.yml">

```yaml
type: task
name: nccl-tests

nodes: 2

image: dstackai/efa
env:
  - NCCL_DEBUG=INFO
commands:
  - |
    # We use FIFO for inter-node communication
    FIFO=/tmp/dstack_job
    if [ ${DSTACK_NODE_RANK} -eq 0 ]; then
      cd /root/nccl-tests/build
      # Generate hostfile for mpirun
      : > hostfile
      for ip in ${DSTACK_NODES_IPS}; do
        echo "${ip} slots=${DSTACK_GPUS_PER_NODE}" >> hostfile
      done
      MPIRUN='mpirun --allow-run-as-root --hostfile hostfile'
      # Wait for other nodes
      while true; do
        if ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 true >/dev/null 2>&1; then
          break
        fi
        echo 'Waiting for nodes...'
        sleep 5
      done
      # Run NCCL tests
      ${MPIRUN} \
        -n ${DSTACK_GPUS_NUM} -N ${DSTACK_GPUS_PER_NODE} \
        --mca pml ^cm \
        --mca btl tcp,self \
        --mca btl_tcp_if_exclude lo,docker0 \
        --bind-to none \
        ./all_reduce_perf -b 8 -e 8G -f 2 -g 1
      # Notify nodes the job is done
      ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 sh -c "echo done > ${FIFO}"
    else
      mkfifo ${FIFO}
      # Wait for a message from the first node
      cat ${FIFO}
    fi

resources:
  gpu: nvidia:4:16GB
  shm_size: 16GB

```

</div>

The master node (`DSTACK_NODE_RANK=0`) generates a `hostfile` listing all node IPs and waits until all nodes are
reachable via MPI. Once confirmed, it launches the `/root/nccl-tests/build/all_reduce_perf` benchmark across all available GPUs in the cluster.

Non-master nodes remain blocked until they receive a termination signal from the master node via a FIFO pipe.

With this, now you can use such a task to run both NCCL or RCCL tests on both cloud and SSH fleets, 
as well as use MPI for other tasks.

> The `dstackai/efa` image used in the example comes with MPI and NCCL tests pre-installed. While it is optimized for
> [AWS EFA :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}, it can also
> be used with regular TCP/IP network adapters and InfiniBand. 
> See the [source code :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/docker/efa) for the image.

!!! info "What's next?"
    1. Learn more about [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md), and [fleets](../../docs/concepts/fleets.md)
    2. Check the [NCCL tests](../../examples/clusters/nccl-tests/index.md) example
    3. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
