# NCCL tests

This example shows how to run distributed [NCCL tests :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/nccl-tests){:target="_blank"} with MPI using `dstack`.

## Running as a task

Here's an example of a task that runs AllReduce test on 2 nodes, each with 4 GPUs (8 processes in total).

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

!!! info "MPI"
    NCCL tests rely on MPI to run on multiple processes. The master node (`DSTACK_NODE_RANK=0`) generates `hostfile` (using `DSTACK_NODES_IPS`) 
    and waits until worker nodes are accessible via MPI. 
    Then, it executes `/nccl-tests/build/all_reduce_perf` across all GPUs.

    Worker nodes use a `FIFO` pipe to wait for until the MPI run is finished.

    There is an open [issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/2467){:target="_blank"} to simplify the use of MPI with distributed tasks.

!!! info "Docker image"
    The `dstackai/efa` image used in the example comes with MPI and NCCL tests pre-installed. While it is optimized for
    [AWS EFA :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}, it can also
    be used with regular TCP/IP network adapters and InfiniBand. 
    
    See the [source code :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/docker/efa) for the image.

### Apply a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply/) command.

<div class="termy">

```shell
$ dstack apply -f examples/distributed-training/nccl-tests/.dstack.yml

 #  BACKEND  REGION     INSTANCE       RESOURCES                                   SPOT  PRICE
 1  aws      us-east-1  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 2  aws      us-west-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 3  aws      us-east-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912

Submit the run nccl-tests? [y/n]: y
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/distributed-training/nccl-tests` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/nccl-tests).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
