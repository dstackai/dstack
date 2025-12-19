---
title: Distributed workload orchestration on Lambda with dstack
---

# Lambda

[Lambda](https://lambda.ai/) offers two ways to use clusters with a fast interconnect:

* [Kubernetes](#kubernetes) – Lets you interact with clusters through the Kubernetes API and includes support for NVIDIA GPU operators and related tools.
* [1-Click Clusters (1CC)](#1-click-clusters) – Gives you direct access to clusters in the form of bare-metal nodes.

Both options use the same underlying networking infrastructure. This example walks you through how to set up Lambda clusters to use with `dstack`.

## Kubernetes

!!! info "Prerequsisites"
    1. Follow the instructions in [Lambda's guide](https://docs.lambda.ai/public-cloud/1-click-clusters/managed-kubernetes/#accessing-mk8s) on accessing MK8s.
    2. Go to `Firewall` → `Edit rules`, click `Add rule`, and allow ingress traffic on port `30022`. This port will be used by the `dstack` server to access the jump host.

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

<div editor-title="lambda-fleet.dstack.yml">
    
```yaml
type: fleet
name: lambda-fleet

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
$ dstack apply -f lambda-fleet.dstack.yml
```

</div>

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

## 1-Click Clusters

Another way to work with Lambda clusters is through [1CC](https://lambda.ai/1-click-clusters). While `dstack` supports automated cluster provisioning via [VM-based backends](https://dstack.ai/docs/concepts/backends#vm-based), there is currently no programmatic way to provision Lambda 1CCs. As a result, to use a 1CC cluster with `dstack`, you must use [SSH fleets](https://dstack.ai/docs/concepts/fleets).

!!! info "Prerequsisites"
    1.  Follow the instructions in [Lambda's guide](https://docs.lambda.ai/public-cloud/1-click-clusters/) on working with 1-Click Clusters

### Create a fleet

Follow the standard instructions for setting up an [SSH fleet](https://dstack.ai/docs/concepts/fleets/#ssh-fleets):

<div editor-title="lambda-fleet.dstack.yml"> 
    
```yaml
type: fleet
name: lambda-fleet

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - worker-gpu-8x-b200-rplfm-ll9nr
    - worker-gpu-8x-b200-rplfm-qrcs9
  proxy_jump:
    hostname: 192.222.55.54
    user: ubuntu
    identity_file: ~/.ssh/id_rsa

placement: cluster
```
    
</div>

> Under `proxy_jump`, we specify the hostname of the head node along with the private SSH key.

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f lambda-fleet.dstack.yml
```

</div>

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

## Run tasks

To run tasks on a cluster, you must use [distributed tasks](https://dstack.ai/docs/concepts/tasks#distributed-task).

### Run NCCL tests

To validate cluster network bandwidth, use the following task:

<div editor-title="lambda-nccl-tests.dstack.yml">

```yaml
type: task
name: nccl-tests

nodes: 2
startup_order: workers-first
stop_criteria: master-done

commands:
  - |
    if [ $DSTACK_NODE_RANK -eq 0 ]; then
      mpirun \
        --allow-run-as-root \
        --hostfile $DSTACK_MPI_HOSTFILE \
        -n $DSTACK_GPUS_NUM \
        -N $DSTACK_GPUS_PER_NODE \
        --bind-to none \
        -x NCCL_IB_HCA=^mlx5_0 \
        /opt/nccl-tests/build/all_reduce_perf -b 8 -e 2G -f 2 -t 1 -g 1 -c 1 -n 100
    else
      sleep infinity
    fi

# Uncomment if the `kubernetes` backend requires it for `/dev/infiniband` access
#privileged: true

resources:
  gpu: nvidia:B200:8
  shm_size: 16GB
```

</div>

Pass the configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f lambda-nccl-tests.dstack.yml

Provisioning...
---> 100%

# nccl-tests version 2.17.6 nccl-headers=22602 nccl-library=22602
# Collective test starting: all_reduce_perf
#
#       size         count      type   redop    root     time   algbw   busbw  #wrong     time   algbw   busbw  #wrong
#        (B)    (elements)                               (us)  (GB/s)  (GB/s)             (us)  (GB/s)  (GB/s)
           8             2     float     sum      -1    36.50    0.00    0.00       0    36.16    0.00    0.00       0
          16             4     float     sum      -1    35.55    0.00    0.00       0    35.49    0.00    0.00       0
          32             8     float     sum      -1    35.49    0.00    0.00       0    36.28    0.00    0.00       0
          64            16     float     sum      -1    35.85    0.00    0.00       0    35.54    0.00    0.00       0
         128            32     float     sum      -1    37.36    0.00    0.01       0    36.82    0.00    0.01       0
         256            64     float     sum      -1    37.38    0.01    0.01       0    37.80    0.01    0.01       0
         512           128     float     sum      -1    51.05    0.01    0.02       0    37.17    0.01    0.03       0
        1024           256     float     sum      -1    45.33    0.02    0.04       0    37.98    0.03    0.05       0
        2048           512     float     sum      -1    38.67    0.05    0.10       0    38.30    0.05    0.10       0
        4096          1024     float     sum      -1    40.08    0.10    0.19       0    39.18    0.10    0.20       0
        8192          2048     float     sum      -1    42.13    0.19    0.36       0    41.47    0.20    0.37       0
       16384          4096     float     sum      -1    43.66    0.38    0.70       0    41.94    0.39    0.73       0
       32768          8192     float     sum      -1    45.42    0.72    1.35       0    43.29    0.76    1.42       0
       65536         16384     float     sum      -1    44.59    1.47    2.76       0    43.90    1.49    2.80       0
      131072         32768     float     sum      -1    47.44    2.76    5.18       0    46.79    2.80    5.25       0
      262144         65536     float     sum      -1    66.68    3.93    7.37       0    65.36    4.01    7.52       0
      524288        131072     float     sum      -1   240.71    2.18    4.08       0   125.73    4.17    7.82       0
     1048576        262144     float     sum      -1   115.58    9.07   17.01       0   115.48    9.08   17.03       0
     2097152        524288     float     sum      -1   114.44   18.33   34.36       0   114.27   18.35   34.41       0
     4194304       1048576     float     sum      -1   118.25   35.47   66.50       0   117.11   35.82   67.15       0
     8388608       2097152     float     sum      -1   141.39   59.33  111.24       0   134.95   62.16  116.55       0
    16777216       4194304     float     sum      -1   186.86   89.78  168.34       0   184.39   90.99  170.60       0
    33554432       8388608     float     sum      -1   255.79  131.18  245.96       0   253.88  132.16  247.81       0
    67108864      16777216     float     sum      -1   350.41  191.52  359.09       0   350.71  191.35  358.79       0
   134217728      33554432     float     sum      -1   596.75  224.92  421.72       0   595.37  225.44  422.69       0
   268435456      67108864     float     sum      -1   934.67  287.20  538.50       0   931.37  288.22  540.41       0
   536870912     134217728     float     sum      -1  1625.63  330.25  619.23       0  1687.31  318.18  596.59       0
  1073741824     268435456     float     sum      -1  2972.25  361.26  677.35       0  2971.33  361.37  677.56       0
  2147483648     536870912     float     sum      -1  5784.75  371.23  696.06       0  5728.40  374.88  702.91       0
# Out of bounds values : 0 OK
# Avg bus bandwidth    : 137.179
```

</div>

## What's next

1. Learn about [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), [services](https://dstack.ai/docs/concepts/services)
2. Read the [Kuberentes](https://dstack.ai/docs/guides/kubernetes), and [Clusters](https://dstack.ai/docs/guides/clusters) guides
3. Check Lambda's docs on [Kubernetes](https://docs.lambda.ai/public-cloud/1-click-clusters/managed-kubernetes/#accessing-mk8s) and [1CC](https://docs.lambda.ai/public-cloud/1-click-clusters/)
