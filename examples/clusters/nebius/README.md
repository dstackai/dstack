---
title: Nebius
description: Using Nebius clusters with InfiniBand support via VMs or Kubernetes
---

# Nebius

`dstack` allows you to use Nebius clusters with fast interconnects in two ways:

* [VMs](#vms) – If you configure a `nebius` backend in `dstack` by providing your Nebius credentials, `dstack` lets you fully provision and use clusters through `dstack`.
* [Kubernetes](#kubernetes) – If you create a Kubernetes cluster on Nebius and configure a `kubernetes` backend and create a backend fleet in `dstack`, `dstack` lets you fully use this cluster through `dstack`.

## VMs

Since `dstack` offers a VM-based backend that natively integrates with Nebius, you only need to provide your Nebius credentials to `dstack`, and it will allow you to fully provision and use clusters on Nebius through `dstack`.

### Configure a backend

You can configure the `nebius` backend using a credentials file [generated](https://docs.nebius.com/iam/service-accounts/authorized-keys#create) by the `nebius` CLI:

<div class="termy">

```shell
$ nebius iam auth-public-key generate \
    --service-account-id &lt;service account ID&gt; \
    --output ~/.nebius/sa-credentials.json
```

</div>

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: nebius
      creds:
        type: service_account
        filename: ~/.nebius/sa-credentials.json
```

</div>

### Create a fleet

Once the backend configured, you can create a fleet:

<div editor-title="nebius-fleet.dstack.yml">
        
```yaml
type: fleet
name: nebius-fleet

nodes: 2
placement: cluster

backends: [nebius]

resources:
  gpu: H100:8
```
        
</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f nebius-fleet.dstack.yml
```

</div>

This will automatically create a Nebius cluster and provision instances. 

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

> If you want instances to be provisioned on demand, you can set `nodes` to `0..2`. In this case, `dstack` will create instances only when you run workloads.

## Kubernetes

If, for some reason, you’d like to use dstack with Nebius’s managed Kubernetes service, you can point `dstack` to the cluster’s kubeconfig file, and `dstack` will allow you to fully use this cluster through `dstack`.

### Create a cluster

1. Go to `Compute` → `Kubernetes` and click `Create cluster`. Make sure to enable `Public endpoint`.
2. Go to `Node groups` and click `Create node group`. Make sure to enable `Assign public IPv4 addresses` and `Install NVIDIA GPU drivers and other components`. Select the appropriate instance type, specify the `Number of nodes`, and set `Node storage` to at least `100GB`. Make sure to click `Create` under `GPU cluster` if you plan to use a fast interconnect.
3. Go to `Applications`, find `NVIDIA Device Plugin`, and click `Deploy`.
4. Wait until the nodes are provisioned.

> Even if you enable `autoscaling`, `dstack` can use only the nodes that are already provisioned. To provision instances on demand, use [VMs](#vms) (see above).

#### Configure the kubeconfig file

1. Click `How to connect` and copy the `nebius` CLI command that configures the `kubeconfig` file.
2. Install the `nebius` CLI and run the command:

<div class="termy">

```shell
$ nebius mk8s cluster get-credentials --id &lt;cluster id&gt; --external
```

</div>

### Configure a backend

Follow the standard instructions for setting up a [`kubernetes`](https://dstack.ai/docs/concepts/backends/#kubernetes) backend:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
      - type: kubernetes
        kubeconfig:
          filename: <kubeconfig path>
```

</div>

### Create a fleet

Once the cluster and the `dstack` server are running, you can create a fleet:

<div editor-title="nebius-fleet.dstack.yml">
    
```yaml
type: fleet
name: nebius-fleet

placement: cluster
nodes: 0..

backends: [kubernetes]

resources:
  # Specify requirements to filter nodes
  gpu: 8
```
    
</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f nebius-fleet.dstack.yml
```

</div>

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

## NCCL tests

Use a [distributed task](https://dstack.ai/docs/concepts/tasks#distributed-tasks) to run NCCL tests and validate the cluster’s network bandwidth.

<div editor-title="nccl-tests.dstack.yml">

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

# Required for `/dev/infiniband` access
privileged: true

resources:
  gpu: 8
  shm_size: 16GB
```

</div>

Pass the configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f crusoe-nccl-tests.dstack.yml

Provisioning...
---> 100%

nccl-tests provisioning completed (running)

 out-of-place                       in-place
        size         count      type   redop    root     time   algbw   busbw  #wrong     time   algbw   busbw  #wrong
        (B)    (elements)                               (us)  (GB/s)  (GB/s)             (us)  (GB/s)  (GB/s)
           8             2     float     sum      -1    45.72    0.00    0.00       0    29.78    0.00    0.00       0
          16             4     float     sum      -1    29.92    0.00    0.00       0    29.42    0.00    0.00       0
          32             8     float     sum      -1    30.10    0.00    0.00       0    29.75    0.00    0.00       0
          64            16     float     sum      -1    34.48    0.00    0.00       0    29.36    0.00    0.00       0
         128            32     float     sum      -1    30.38    0.00    0.01       0    29.67    0.00    0.01       0
         256            64     float     sum      -1    30.48    0.01    0.02       0    29.97    0.01    0.02       0
         512           128     float     sum      -1    30.45    0.02    0.03       0    30.85    0.02    0.03       0
        1024           256     float     sum      -1    31.36    0.03    0.06       0    31.29    0.03    0.06       0
        2048           512     float     sum      -1    32.27    0.06    0.12       0    32.26    0.06    0.12       0
        4096          1024     float     sum      -1    36.04    0.11    0.21       0    43.17    0.09    0.18       0
        8192          2048     float     sum      -1    37.24    0.22    0.41       0    35.54    0.23    0.43       0
       16384          4096     float     sum      -1    37.22    0.44    0.83       0    34.55    0.47    0.89       0
       32768          8192     float     sum      -1    43.82    0.75    1.40       0    35.64    0.92    1.72       0
       65536         16384     float     sum      -1    37.85    1.73    3.25       0    37.55    1.75    3.27       0
      131072         32768     float     sum      -1    43.10    3.04    5.70       0    53.08    2.47    4.63       0
      262144         65536     float     sum      -1    58.59    4.47    8.39       0    63.33    4.14    7.76       0
      524288        131072     float     sum      -1    97.88    5.36   10.04       0    83.91    6.25   11.72       0
     1048576        262144     float     sum      -1    87.08   12.04   22.58       0    77.82   13.47   25.26       0
     2097152        524288     float     sum      -1    99.06   21.17   39.69       0    97.67   21.47   40.26       0
     4194304       1048576     float     sum      -1   110.14   38.08   71.40       0   114.66   36.58   68.59       0
     8388608       2097152     float     sum      -1   154.48   54.30  101.82       0   156.03   53.76  100.80       0
    16777216       4194304     float     sum      -1   210.33   79.77  149.56       0   200.98   83.48  156.52       0
    33554432       8388608     float     sum      -1   274.23  122.36  229.43       0   276.45  121.38  227.58       0
    67108864      16777216     float     sum      -1   472.43  142.05  266.35       0   480.00  139.81  262.14       0
   134217728      33554432     float     sum      -1   759.58  176.70  331.31       0   756.21  177.49  332.79       0
   268435456      67108864     float     sum      -1  1305.66  205.59  385.49       0  1303.37  205.95  386.16       0
   536870912     134217728     float     sum      -1  2379.38  225.63  423.06       0  2373.42  226.20  424.13       0
  1073741824     268435456     float     sum      -1  4511.97  237.98  446.21       0  4513.82  237.88  446.02       0
  2147483648     536870912     float     sum      -1  8776.26  244.69  458.80       0  8760.42  245.13  459.63       0
  4294967296    1073741824     float     sum      -1  17407.8  246.73  462.61       0  17302.2  248.23  465.44       0
  8589934592    2147483648     float     sum      -1  34448.4  249.36  467.54       0  34381.0  249.85  468.46       0
  Out of bounds values : 0 OK
  Avg bus bandwidth    : 125.499

  Collective test concluded: all_reduce_perf
```

</div>

## What's next

1. Learn about [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), [services](https://dstack.ai/docs/concepts/services)
2. Check out [backends](https://dstack.ai/docs/concepts/backends) and [fleets](https://dstack.ai/docs/concepts/fleets)
3. Read Nebius' docs on [networking for VMs](https://docs.nebius.com/compute/clusters/gpu) and the [managed Kubernetes service](https://docs.nebius.com/kubernetes).
