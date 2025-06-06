# RCCL tests

This example shows how to run distributed [RCCL tests :material-arrow-top-right-thin:{ .external }](https://github.com/ROCm/rccl-tests){:target="_blank"} with MPI using `dstack`.

## Running as a task

Here's an example of a task that runs AllReduce test on 2 nodes, each with 8 `Mi300x` GPUs (16 processes in total).

<div editor-title="examples/distributed-training/rccl-tests/.dstack.yml">

```yaml
type: task
name: rccl-tests

nodes: 2
startup_order: workers-first
stop_criteria: master-done

# Mount the system libraries folder from the host
volumes:
  - /usr/local/lib:/mnt/lib

image: rocm/dev-ubuntu-22.04:6.4-complete
env:
  - NCCL_DEBUG=INFO
  - OPEN_MPI_HOME=/usr/lib/x86_64-linux-gnu/openmpi
commands:
  # Setup MPI and build RCCL tests
  - apt-get install -y git libopenmpi-dev openmpi-bin
  - git clone https://github.com/ROCm/rccl-tests.git
  - cd rccl-tests
  - make MPI=1 MPI_HOME=$OPEN_MPI_HOME

  # Preload the RoCE driver library from the host (for Broadcom driver compatibility)
  - export LD_PRELOAD=/mnt/lib/libbnxt_re-rdmav34.so

  # Run RCCL tests via MPI
  - |
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      mpirun --allow-run-as-root \
        --hostfile $DSTACK_MPI_HOSTFILE \
        -n $DSTACK_GPUS_NUM \
        -N $DSTACK_GPUS_PER_NODE \
        --mca btl_tcp_if_include ens41np0 \
        -x LD_PRELOAD \
        -x NCCL_IB_HCA=mlx5_0/1,bnxt_re0,bnxt_re1,bnxt_re2,bnxt_re3,bnxt_re4,bnxt_re5,bnxt_re6,bnxt_re7 \
        -x NCCL_IB_GID_INDEX=3 \
        -x NCCL_IB_DISABLE=0 \
        ./build/all_reduce_perf -b 8M -e 8G -f 2 -g 1 -w 5 --iters 20 -c 0;
    else
      sleep infinity
    fi

resources:
  gpu: MI300X:8
```

</div>

!!! info "MPI"
    RCCL tests rely on MPI to run on multiple processes. The master node (`DSTACK_NODE_RANK=0`) generates `hostfile` (using `DSTACK_NODES_IPS`) 
    and waits until other nodes are accessible via MPI. 
    Then, it executes `/rccl-tests/build/all_reduce_perf` across all GPUs.

    Other nodes use a `FIFO` pipe to wait for until the MPI run is finished.

    There is an open [issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/2467){:target="_blank"} to simplify the use of MPI with distributed tasks.

!!! info "RoCE library"
    Broadcom RoCE drivers require the `libbnxt_re` userspace library inside the container to be compatible with the host’s Broadcom 
    kernel driver `bnxt_re`. To ensure this compatibility, we mount `libbnxt_re-rdmav34.so` from the host and preload it 
    using `LD_PRELOAD` when running MPI.

### Creating a fleet

Define an SSH fleet configuration by listing the IP addresses of each node in the cluster, along with the SSH user and SSH key configured for each host.

```yaml
type: fleet
# The name is optional, if not specified, generated randomly
name: mi300x-fleet

# SSH credentials for the on-prem servers
ssh_config:
  user: root
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 144.202.58.28
    - 137.220.58.52
```

### Apply a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply/) command.

<div class="termy">

```shell
$ dstack apply -f examples/distributed-training/rccl-tests/.dstack.yml

 #  BACKEND       RESOURCES                      INSTANCE TYPE   PRICE
 1  ssh (remote)  cpu=256 mem=2268GB disk=752GB  instance        $0      idle
                  MI300X:192GB:8
 2  ssh (remote)  cpu=256 mem=2268GB disk=752GB  instance        $0      idle
                  MI300X:192GB:8

Submit the run rccl-tests? [y/n]: y
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/distributed-training/rccl-tests` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/rccl-tests).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
