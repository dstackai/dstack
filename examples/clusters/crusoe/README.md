---
title: Crusoe
description: Using Crusoe clusters with InfiniBand support via VMs or Kubernetes
---

# Crusoe

`dstack` allows using Crusoe clusters with fast interconnect via two ways:

* [VMs](#vms) – If you configure a `crusoe` backend in `dstack` by providing your Crusoe credentials, `dstack` lets you fully provision and use clusters through `dstack`.
* [Kubernetes](#kubernetes) – If you create a Kubernetes cluster on Crusoe and configure a `kubernetes` backend and create a backend fleet in `dstack`, `dstack` lets you fully use this cluster through `dstack`.

## VMs

Since `dstack` offers a VM-based backend that natively integrates with Crusoe, you only need to provide your Crusoe credentials to `dstack`, and it will allow you to fully provision and use clusters on Crusoe through `dstack`.

### Configure a backend

Log into your [Crusoe Cloud](https://console.crusoecloud.com/) console, create an API key under your account settings, and note your project ID.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
    - type: crusoe
      project_id: your-project-id
      creds:
        type: access_key
        access_key: your-access-key
        secret_key: your-secret-key
```

</div>

### Create a fleet

Once the backend is configured, you can create a fleet:

<div editor-title="crusoe-fleet.dstack.yml">
    
```yaml
type: fleet
name: crusoe-fleet

nodes: 2
placement: cluster

backends: [crusoe]

resources:
  gpu: A100:80GB:8
```
    
</div>

Pass the fleet configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f crusoe-fleet.dstack.yml
```

</div>

This will automatically create an IB partition and provision instances with InfiniBand networking.

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

> If you want instances to be provisioned on demand, you can set `nodes` to `0..2`. In this case, `dstack` will create instances only when you run workloads.

## Kubernetes

### Create a cluster

1. Go `Networking` → `Firewall Rules`, click `Create Firewall Rule`, and allow ingress traffic on port `30022`. This port will be used by the `dstack` server to access the jump host.
2. Go to `Orchestration` and click `Create Cluster`. Make sure to enable the `NVIDIA GPU Operator` add-on.
3. Go the the cluster, and click `Create Node Pool`. Select the right type of the instance, and  `Desired Number of Nodes`.
4. Wait until nodes are provisioned.

> Even if you enable `autoscaling`, `dstack` can use only the nodes that are already provisioned.

### Configure the backend

Follow the standard instructions for setting up a [`kubernetes`](https://dstack.ai/docs/concepts/backends/#kubernetes) backend:

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

Once the Crusoe Managed Kubernetes cluster and the `dstack` server are running, you can create a fleet:

<div editor-title="crusoe-fleet.dstack.yml">
    
```yaml
type: fleet
name: crusoe-fleet

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
$ dstack apply -f crusoe-fleet.dstack.yml
```

</div>

Once the fleet is created, you can run [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), and [services](https://dstack.ai/docs/concepts/services).

## NCCL tests

Use a [distributed task](https://dstack.ai/docs/concepts/tasks#distributed-tasks) that runs NCCL tests to validate cluster network bandwidth.

=== "VMs"

    With the Crusoe backend, HPC-X and NCCL topology files are pre-installed on the host VM image. Mount them into the container via [instance volumes](https://dstack.ai/docs/concepts/volumes#instance-volumes).

    <div editor-title="crusoe-nccl-tests.dstack.yml">

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
            -x NCCL_IB_HCA=^mlx5_0:1 \
            /opt/nccl-tests/build/all_reduce_perf -b 8 -e 2G -f 2 -t 1 -g 1 -c 1 -n 100
        else
          sleep infinity
        fi

    backends: [crusoe]

    resources:
      gpu: A100:80GB:8
      shm_size: 16GB
    ```

    </div>

    > Update `NCCL_TOPO_FILE` to match your instance type. Topology files for all supported types are available at `/etc/crusoe/nccl_topo/` on the host.

=== "Kubernetes"

    If you're running on Crusoe Managed Kubernetes, make sure to install HPC-X and provide an up-to-date topology file. 

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
        When running on Crusoe Managed Kubernetes, set `privileged` to `true` to ensure access to InfiniBand.

Pass the configuration to `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f crusoe-nccl-tests.dstack.yml
```

</div>

## What's next

1. Learn about [dev environments](https://dstack.ai/docs/concepts/dev-environments), [tasks](https://dstack.ai/docs/concepts/tasks), [services](https://dstack.ai/docs/concepts/services)
2. Check out [backends](https://dstack.ai/docs/concepts/backends#crusoe-cloud) and [fleets](https://dstack.ai/docs/concepts/fleets#cloud-fleets)
3. Check the docs on [Crusoe's networking](https://docs.crusoecloud.com/networking/infiniband/) and ["Crusoe Managed" Kubernetes](https://docs.crusoecloud.com/orchestration/cmk/index.html)
