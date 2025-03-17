# NCCL Tests

This example shows how to run distributed [NCCL Tests :material-arrow-top-right-thin:{ .external }](https://github.com/NVIDIA/nccl-tests){:target="_blank"} with MPI using `dstack`.

??? info "AWS EFA"
    The used image is optimized for AWS [EFA :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"} but works with regular TCP/IP network adapters as well.

## Configuration

This configuration runs AllReduce test on 2 nodes with 4 GPUs each (8 processes total), but you can adjust both `nodes` and `resources.gpu` without modifying the script.

<div editor-title="examples/misc/nccl-tests/.dstack.yml">

```yaml
type: task
name: nccl-tests

image: un1def/aws-efa-test
nodes: 2

env:
  - NCCL_DEBUG=INFO

commands:
  - |
    # We use FIFO for inter-node communication
    FIFO=/tmp/dstack_job
    if [ ${DSTACK_NODE_RANK} -eq 0 ]; then
      cd /root/nccl-tests/build
      echo "${DSTACK_NODES_IPS}" > hostfile
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

### Running a configuration

To run a configuration, use the [`dstack apply`](https://dstack.ai/docs/reference/cli/dstack/apply/) command.

<div class="termy">

```shell
$ dstack apply -f examples/misc/nccl-tests/.dstack.yml

 #  BACKEND  REGION     INSTANCE       RESOURCES                                   SPOT  PRICE
 1  aws      us-east-1  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 2  aws      us-west-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912
 3  aws      us-east-2  g4dn.12xlarge  48xCPU, 192GB, 4xT4 (16GB), 100.0GB (disk)  no    $3.912

Submit the run nccl-tests? [y/n]: y
```

</div>
