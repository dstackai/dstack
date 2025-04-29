# RCCL tests

This example shows how to run distributed [RCCL tests :material-arrow-top-right-thin:{ .external }](https://github.com/ROCm/rccl-tests){:target="_blank"} with MPI using `dstack`.

## Running as a task

Here's an example of a task that runs AllReduce test on 2 nodes, each with 8 `Mi300x` GPUs (16 processes in total).

<div editor-title="examples/cluster/rccl-tests/.dstack.yml">

```yaml
type: task
name: rccl-tests
nodes: 2

image: rocm/dev-ubuntu-22.04:6.4-complete
env:
  - NCCL_DEBUG=INFO
  - MPI_HOME=/usr/lib/x86_64-linux-gnu/openmpi
commands:
  # Setup MPI
  - apt-get install -y git libopenmpi-dev openmpi-bin
  # Build RCCL Tests
  - git clone https://github.com/ROCm/rccl-tests.git
  - cd rccl-tests
  - make MPI=1 MPI_HOME=$MPI_HOME
  - |
    FIFO=/tmp/dstack_job
    if [ ${DSTACK_NODE_RANK} -eq 0 ]; then
      sleep 10
      echo "$DSTACK_NODES_IPS" | tr ' ' '\n' > hostfile
      MPIRUN='mpirun --allow-run-as-root --hostfile hostfile'
      # Wait for other nodes
      while true; do
        if ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 true >/dev/null 2>&1; then
          break
        fi
        echo 'Waiting for nodes...'
        sleep 5
      done
      # Run NCCL Tests
      ${MPIRUN} \
        -n ${DSTACK_GPUS_NUM} -N ${DSTACK_GPUS_PER_NODE} \
        --mca btl_tcp_if_include ens41np0 \
        -x LD_PRELOAD=/workflow/libibverbs/libbnxt_re-rdmav34.so \
        -x NCCL_IB_HCA=mlx5_0/1,bnxt_re0,bnxt_re1,bnxt_re2,bnxt_re3,bnxt_re4,bnxt_re5,bnxt_re6,bnxt_re7 \
        -x NCCL_IB_GID_INDEX=3 \
        -x NCCL_IB_DISABLE=0 \
        ./build/all_reduce_perf -b 8M -e 8G -f 2 -g 1 -w 5 --iters 20 -c 0;
      # Notify nodes the job is done
      ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 sh -c "echo done > ${FIFO}"
    else
      mkfifo ${FIFO}
      # Wait for a message from the first node
      cat ${FIFO}
    fi
resources:
  gpu: mi300x:8

# Mount Broadcom driver compatible libibverbs binary
volumes:
  - /usr/local/lib/libbnxt_re-rdmav34.so:/workflow/libibverbs/libbnxt_re-rdmav34.so
```

</div>

The script orchestrates distributed execution across multiple nodes using MPI. The master node (identified by
`DSTACK_NODE_RANK=0`) generates `hostfile` listing all node IPs and continuously checks until all worker nodes are
accessible via MPI. Once confirmed, it executes the `/rccl-tests/build/all_reduce_perf` benchmark script across all available GPUs.

Worker nodes use a FIFO pipe to block execution until they receive a termination signal from the master
node. This ensures worker nodes remain active during the test and only exit once the master node completes the
benchmark.

> The `rocm/dev-ubuntu-22.04:6.4-complete` image used in the example comes with ROCm 6.4 and RCCL.
> Broadcom’s kernel driver `bnxt_re` should match the corresponding RoCE userspace library `libbnxt_re`. 
> To ensure this, we mount the host’s `libbnxt_re-rdmav34.so` into the container and preload it using `LD_PRELOAD`. 
> This guarantees that the container uses the exact library version bundled with the host driver. Without this, an ABI mismatch occurs.

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
$ dstack apply -f examples/cluster/rccl-tests/.dstack.yml

 #  BACKEND      RESOURCES                                    INSTANCE TYPE  PRICE
 1  ssh (remote) cpu=256 mem=2268GB disk=752GB MI300X:192GB:8  instance      $0     idle
 2  ssh (remote) cpu=256 mem=2268GB disk=752GB MI300X:192GB:8  instance      $0     idle

Submit the run rccl-tests? [y/n]: y
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/cluster/rccl-tests` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/cluster/rccl-tests).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/dev-environments), [tasks](https://dstack.ai/docs/tasks), 
   [services](https://dstack.ai/docs/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
