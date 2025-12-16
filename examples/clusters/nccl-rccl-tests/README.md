# NCCL/RCCL tests

This example shows how to run [NCCL](https://github.com/NVIDIA/nccl-tests) or [RCCL](https://github.com/ROCm/rccl-tests) tests on a cluster using [distributed tasks](https://dstack.ai/docs/concepts/tasks#distributed-tasks).

!!! info "Prerequisites"
    Before running a distributed task, make sure to create a fleet with `placement` set to `cluster` (can be a [managed fleet](https://dstack.ai/docs/concepts/fleets#backend-placement) or an [SSH fleet](https://dstack.ai/docs/concepts/fleets#ssh-placement)).

## Running as a task

Here's an example of a task that runs AllReduce test on 2 nodes, each with 4 GPUs (8 processes in total).

=== "NCCL tests"

    <div editor-title="examples/clusters/nccl-rccl-tests/nccl-tests.dstack.yml">

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

    # Uncomment if the `kubernetes` backend requires it for `/dev/infiniband` access
    #privileged: true

    resources:
      gpu: nvidia:1..8
      shm_size: 16GB
    ```

    </div>

    !!! info "Default image"
        If you don't specify `image`, `dstack` uses its [base](https://github.com/dstackai/dstack/tree/master/docker/base) Docker image pre-configured with 
        `uv`, `python`, `pip`, essential CUDA drivers, `mpirun`, and NCCL tests (under `/opt/nccl-tests/build`). 

=== "RCCL tests"

    <div editor-title="examples/clusters/nccl-rccl-tests/rccl-tests.dstack.yml">

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

    !!! info "RoCE library"
        Broadcom RoCE drivers require the `libbnxt_re` userspace library inside the container to be compatible with the host’s Broadcom 
        kernel driver `bnxt_re`. To ensure this compatibility, we mount `libbnxt_re-rdmav34.so` from the host and preload it 
        using `LD_PRELOAD` when running MPI.


!!! info "Privileged"
    In some cases, the backend (e.g., `kubernetes`) may require `privileged: true` to access the high-speed interconnect (e.g., InfiniBand).

### Apply a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply/) command.

<div class="termy">

```shell
$ dstack apply -f examples/clusters/nccl-rccl-tests/nccl-tests.dstack.yml

 #  BACKEND  REGION     INSTANCE       RESOURCES                                   SPOT  PRICE
 1  aws      us-east-1  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 2  aws      us-west-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 3  aws      us-east-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912

Submit the run nccl-tests? [y/n]: y
```

</div>

## Source code

The source-code of this example can be found in 
[`examples/clusters/nccl-rccl-tests`](https://github.com/dstackai/dstack/blob/master/examples/clusters/nccl-rccl-tests).

## What's next?

1. Check [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), 
   [services](https://dstack.ai/docsconcepts/services), and [fleets](https://dstack.ai/docs/concepts/fleets).
