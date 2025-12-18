---
title: Distributed workload orchestration on Crusoe with dstack
---

# Crusoe

Crusoe offers two ways to use clusters with fast interconnect:

* [Kubernetes](#kubernetes) – Lets you interact with clusters through the Kubernetes API and includes support for NVIDIA GPU operators and related tools.
* [Virtual Machines (VMs)](#vms) – Gives you direct access to clusters in the form of virtual machines.

Both options use the same underlying networking infrastructure. This example walks you through how to set up Crusoe clusters to use with `dstack`.

## Kubernetes

!!! info "Prerequsisites"
    1. Go `Networking` → `Firewall Rules`, click `Create Firewall Rule`, and allow ingress traffic on port `30022`. This port will be used by the `dstack` server to access the jump host.
    2. Go to `Orchestration` and click `Create Cluster`. Make sure to enable the `NVIDIA GPU Operator` add-on.
    3. Go the the cluster, and click `Create Node Pool`. Select the right type of the instance. If you intend to auto-scale the cluster, make sure to set `Desired Number of Nodes` at least to `1`, since `dstack` doesn't currently support clusters that scale down to `0` nodes.
    4. Wait until at least one node is running.

### Configure the backend

Follow the standard instructions for setting up a [Kubernetes](https://dstack.ai/docs/concepts/backends/#kubernetes) backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
    - type: kubernetes
      kubeconfig:
        filename: <kubeconfig path>
      proxy_jump:
        port: 30022
```

</div>

### Create a fleet

Once the Kubernetes cluster and the `dstack` server are running, you can create a fleet:

<div editor-title="crusoe-fleet.dstack.yml">
    
```yaml
type: fleet
name: crusoe-fleet

placement: cluster
nodes: 0..

backends: [kubernetes]

resources:
  # Specify requirements to filter nodes
  gpu: 1..8
```
    
</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f crusoe-fleet.dstack.yml
```

</div>

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

## VMs

Another way to work with Crusoe clusters is through VMs. While `dstack` typically supports VM-based compute providers via [dedicated backends](https://dstack.ai/docs/concepts/backends#vm-based) that automate provisioning, Crusoe does not yet have [such a backend](https://github.com/dstackai/dstack/issues/3378). As a result, to use a VM-based Crusoe cluster with `dstack`, you should use [SSH fleets](https://dstack.ai/docs/concepts/fleets).

!!! info "Prerequsisites"
    1. Go to `Compute`, then `Instances`, and click `Create Instance`. Make sure to select the right instance type and VM image (that [support interconnect](https://docs.crusoecloud.com/networking/infiniband/managing-infiniband-networks/index.html)). Make sure to create as many instances as needed.

### Create a fleet

Follow the standard instructions for setting up an [SSH fleet](https://dstack.ai/docs/concepts/fleets/#ssh-fleets):

<div editor-title="crusoe-fleet.dstack.yml"> 
    
```yaml
type: fleet
name: crusoe-fleet

placement: cluster

# SSH credentials for the on-prem servers
ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 3.255.177.51
    - 3.255.177.52
```
    
</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f crusoe-fleet.dstack.yml
```

</div>

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

## Run NCCL tests

Use a [distributed task](https://dstack.ai/docs/concepts/tasks#distributed-task) that runs NCCL tests to validate cluster network bandwidth.

=== "Kubernetes"

    If you’re running on Crusoe’s Kubernetes, make sure to install HPC-X and provide an up-to-date topology file. 

    <div editor-title="crusoe-nccl-tests.dstack.yml">

    ```yaml
    type: task
    name: nccl-tests

    nodes: 2
    startup_order: workers-first
    stop_criteria: master-done

    commands:
      # Install NCCL topology files
      - curl -sSL https://gist.github.com/un-def/48df8eea222fa9547ad4441986eb15af/archive/df51d56285c5396a0e82bb42f4f970e7bb0a9b65.tar.gz -o nccl_topo.tar.gz
      - mkdir -p /etc/crusoe/nccl_topo
      - tar -C /etc/crusoe/nccl_topo -xf nccl_topo.tar.gz --strip-components=1
      # Install and initialize HPC-X
      - curl -sSL https://content.mellanox.com/hpc/hpc-x/v2.21.3/hpcx-v2.21.3-gcc-doca_ofed-ubuntu22.04-cuda12-x86_64.tbz -o hpcx.tar.bz
      - mkdir -p /opt/hpcx
      - tar -C /opt/hpcx -xf hpcx.tar.bz --strip-components=1 --checkpoint=10000
      - . /opt/hpcx/hpcx-init.sh
      - hpcx_load
      # Run NCCL Tests
      - |
        if [ $DSTACK_NODE_RANK -eq 0 ]; then
          mpirun \
            --allow-run-as-root \
            --hostfile $DSTACK_MPI_HOSTFILE \
            -n $DSTACK_GPUS_NUM \
            -N $DSTACK_GPUS_PER_NODE \
            --bind-to none \
            -mca btl tcp,self \
            -mca coll_hcoll_enable 0 \
            -x PATH \
            -x LD_LIBRARY_PATH \
            -x CUDA_DEVICE_ORDER=PCI_BUS_ID \
            -x NCCL_SOCKET_NTHREADS=4 \
            -x NCCL_NSOCKS_PERTHREAD=8 \
            -x NCCL_TOPO_FILE=/etc/crusoe/nccl_topo/a100-80gb-sxm-ib-cloud-hypervisor.xml \
            -x NCCL_IB_MERGE_VFS=0 \
            -x NCCL_IB_AR_THRESHOLD=0 \
            -x NCCL_IB_PCI_RELAXED_ORDERING=1 \
            -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
            -x NCCL_IB_QPS_PER_CONNECTION=2 \
            -x NCCL_IB_HCA=mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1,mlx5_8:1 \
            -x UCX_NET_DEVICES=mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1,mlx5_8:1 \
            /opt/nccl-tests/build/all_reduce_perf -b 8 -e 2G -f 2 -t 1 -g 1 -c 1 -n 100
        else
          sleep infinity
        fi

    # Required for IB
    privileged: true

    resources:
      gpu: A100:8
      shm_size: 16GB
    ```

    </div>

    > The task above downloads an A100 topology file from a Gist. The most reliable way to obtain the latest topology is to copy it from a Crusoe-provisioned VM (see [VMs](#vms)).
    
    ??? info "Privileged"
        When running on Kubernetes, set `privileged` to `true` to ensure access to InfiniBand.

=== "SSH fleets"

With Crusoe VMs, HPC-X and up-to-date topology files are already available on the hosts. When using SSH fleets, simply mount them via [instance volumes](https://dstack.ai/docs/concepts/volumes#instance-volumes).

```yaml
type: task
name: nccl-tests

nodes: 2
startup_order: workers-first
stop_criteria: master-done

volumes:
  - /opt/hpcx:/opt/hpcx
  - /etc/crusoe/nccl_topo:/etc/crusoe/nccl_topo

commands:
  - . /opt/hpcx/hpcx-init.sh
  - hpcx_load
  # Run NCCL Tests
  - |
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      mpirun \
        --allow-run-as-root \
        --hostfile $DSTACK_MPI_HOSTFILE \
        -n $DSTACK_GPUS_NUM \
        -N $DSTACK_GPUS_PER_NODE \
        --bind-to none \
        -mca btl tcp,self \
        -mca coll_hcoll_enable 0 \
        -x PATH \
        -x LD_LIBRARY_PATH \
        -x CUDA_DEVICE_ORDER=PCI_BUS_ID \
        -x NCCL_SOCKET_NTHREADS=4 \
        -x NCCL_NSOCKS_PERTHREAD=8 \
        -x NCCL_TOPO_FILE=/etc/crusoe/nccl_topo/a100-80gb-sxm-ib-cloud-hypervisor.xml \
        -x NCCL_IB_MERGE_VFS=0 \
        -x NCCL_IB_AR_THRESHOLD=0 \
        -x NCCL_IB_PCI_RELAXED_ORDERING=1 \
        -x NCCL_IB_SPLIT_DATA_ON_QPS=0 \
        -x NCCL_IB_QPS_PER_CONNECTION=2 \
        -x NCCL_IB_HCA=mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1,mlx5_8:1 \
        -x UCX_NET_DEVICES=mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1,mlx5_8:1 \
        /opt/nccl-tests/build/all_reduce_perf -b 8 -e 2G -f 2 -t 1 -g 1 -c 1 -n 100
    else
      sleep infinity
    fi

resources:
  gpu: A100:8
  shm_size: 16GB
```

Pass the configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f crusoe-nccl-tests.dstack.yml

Provisioning...
---> 100%

nccl-tests provisioning completed (running)

#                                                              out-of-place                       in-place
#       size         count      type   redop    root     time   algbw   busbw  #wrong     time   algbw   busbw  #wrong
#        (B)    (elements)                               (us)  (GB/s)  (GB/s)             (us)  (GB/s)  (GB/s)
           8             2     float     sum      -1    27.70    0.00    0.00       0    29.82    0.00    0.00       0
          16             4     float     sum      -1    28.78    0.00    0.00       0    28.99    0.00    0.00       0
          32             8     float     sum      -1    28.49    0.00    0.00       0    28.16    0.00    0.00       0
          64            16     float     sum      -1    28.41    0.00    0.00       0    28.69    0.00    0.00       0
         128            32     float     sum      -1    28.94    0.00    0.01       0    28.58    0.00    0.01       0
         256            64     float     sum      -1    29.46    0.01    0.02       0    29.45    0.01    0.02       0
         512           128     float     sum      -1    30.23    0.02    0.03       0    29.85    0.02    0.03       0
        1024           256     float     sum      -1    30.79    0.03    0.06       0    34.03    0.03    0.06       0
        2048           512     float     sum      -1    37.90    0.05    0.10       0    33.22    0.06    0.12       0
        4096          1024     float     sum      -1    35.91    0.11    0.21       0    35.30    0.12    0.22       0
        8192          2048     float     sum      -1    36.84    0.22    0.42       0    38.30    0.21    0.40       0
       16384          4096     float     sum      -1    47.08    0.35    0.65       0    37.26    0.44    0.82       0
       32768          8192     float     sum      -1    45.20    0.72    1.36       0    48.70    0.67    1.26       0
       65536         16384     float     sum      -1    49.43    1.33    2.49       0    50.97    1.29    2.41       0
      131072         32768     float     sum      -1    51.08    2.57    4.81       0    50.17    2.61    4.90       0
      262144         65536     float     sum      -1   192.78    1.36    2.55       0   100.00    2.62    4.92       0
      524288        131072     float     sum      -1    68.02    7.71   14.45       0    69.40    7.55   14.16       0
     1048576        262144     float     sum      -1    81.71   12.83   24.06       0    88.58   11.84   22.20       0
     2097152        524288     float     sum      -1   113.03   18.55   34.79       0   102.21   20.52   38.47       0
     4194304       1048576     float     sum      -1   123.50   33.96   63.68       0   131.71   31.84   59.71       0
     8388608       2097152     float     sum      -1   189.42   44.29   83.04       0   183.01   45.84   85.95       0
    16777216       4194304     float     sum      -1   274.05   61.22  114.79       0   265.91   63.09  118.30       0
    33554432       8388608     float     sum      -1   490.77   68.37  128.20       0   490.53   68.40  128.26       0
    67108864      16777216     float     sum      -1   854.62   78.52  147.23       0   853.49   78.63  147.43       0
   134217728      33554432     float     sum      -1  1483.43   90.48  169.65       0  1479.22   90.74  170.13       0
   268435456      67108864     float     sum      -1  2700.36   99.41  186.39       0  2700.49   99.40  186.38       0
   536870912     134217728     float     sum      -1  5300.49  101.29  189.91       0  5314.91  101.01  189.40       0
  1073741824     268435456     float     sum      -1  10472.2  102.53  192.25       0  10485.6  102.40  192.00       0
  2147483648     536870912     float     sum      -1  20749.1  103.50  194.06       0  20745.7  103.51  194.09       0
# Out of bounds values : 0 OK
# Avg bus bandwidth    : 53.7387
```

</div>

## What's next

1. Learn about [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), [services](https://dstack.ai/docs/concepts/services)
2. Read the [Kuberentes](https://dstack.ai/docs/guides/kubernetes), and [Clusters](https://dstack.ai/docs/guides/clusters) guides
3. Check Crusoe's docs on [networking](https://docs.crusoecloud.com/networking/infiniband/) and [Kubernetes](https://docs.crusoecloud.com/orchestration/cmk/index.html)
