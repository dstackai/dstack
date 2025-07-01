# NCCL tests

This example shows how to run distributed [NCCL tests :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/nccl-tests){:target="_blank"} with MPI using `dstack`.

## Running as a task

Here's an example of a task that runs AllReduce test on 2 nodes, each with 4 GPUs (8 processes in total).

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
  gpu: nvidia:1..8
  shm_size: 16GB
```

</div>

<!-- TODO: Need to stop using our EFA image - either make our default image cluster-friendly, or recommend using NGC or other images -->

!!! info "Docker image"
    The `dstackai/efa` image used in the example comes with MPI and NCCL tests pre-installed. While it is optimized for
    [AWS EFA :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}, it can also
    be used with regular TCP/IP network adapters and InfiniBand. 
    
    See the [source code :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/docker/efa) for the image.

### Apply a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply/) command.

<div class="termy">

```shell
$ dstack apply -f examples/clusters/nccl-tests/.dstack.yml

 #  BACKEND  REGION     INSTANCE       RESOURCES                                   SPOT  PRICE
 1  aws      us-east-1  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 2  aws      us-west-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 3  aws      us-east-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912

Submit the run nccl-tests? [y/n]: y
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/clusters/nccl-tests` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/clusters/nccl-tests).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
