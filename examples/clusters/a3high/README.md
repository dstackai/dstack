# GCP A3 High

This example shows how to set up a GCP A3 High cluster with [GPUDirect-TCPX](https://cloud.google.com/compute/docs/gpus/gpudirect)
optimized NCCL communication and run [NCCL Tests](https://github.com/NVIDIA/nccl-tests) on it using `dstack`.

## Overview

GCP's A3 High instances are 8xH100 VMs that have 1000Gbps maximum network bandwidth,
which is the second best among GCP H100 instances after A3 Mega.
To get that network performance, you need
to set up GPUDirect-TCPX – the GCP technology for GPU RDMA over TCP. This involves:

* Setting up four extra data NICs on every node, each NIC in a separate VPC.
* Configuring a VM image with the GPUDirect-TCPX support.
* Launching an RXDM service container.
* Installing the GPUDirect-TCPX NCCL plugin.

`dstack` hides most of the setup complexity and provides optimized A3 High clusters out-of-the-box.

!!! info "A3 Edge"
    This guide also applies to A3 Edge instances.

!!! info "A3 Mega"
    A3 Mega instances use GPUDirect-TCPXO, which is an extension of GPUDirect-TCPX.
    See the [A3 Mega guide](https://dstack.ai/examples/distributed-training/a3mega-clusters/) for more details.

## Configure GCP backend

First configure the `gcp` backend for the GPUDirect-TCPX support.
You need to specify at least four `extra_vpcs` to use for data NICs.
You also need to specify `vm_service_account` that's authorized to pull GPUDirect-related Docker images:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
  - name: main
    backends:
    - type: gcp
      project_id: $MYPROJECT # Replace $MYPROJECT
      extra_vpcs:
        - dstack-gpu-data-net-1
        - dstack-gpu-data-net-2
        - dstack-gpu-data-net-3
        - dstack-gpu-data-net-4
      regions: [europe-west4]
      vm_service_account: a3cluster-sa@$MYPROJECT.iam.gserviceaccount.com # Replace $MYPROJECT
      creds:
        type: default
```

</div>

!!! info "Custom VPC"
    If you specify a non-default primary VPC, ensure it has a firewall rule
    allowing all traffic within the VPC. This is needed for MPI and NCCL to work.
    The default VPC already permits traffic within the VPC.

??? info "Create extra VPCs"
    Create the VPC networks for GPUDirect in your project, each with a subnet and a firewall rule:
    
    ```shell
    # Specify the region where you intend to deploy the cluster
    REGION="europe-west4"

    for N in $(seq 1 4); do
    gcloud compute networks create dstack-gpu-data-net-$N \
        --subnet-mode=custom \
        --mtu=8244

    gcloud compute networks subnets create dstack-gpu-data-sub-$N \
        --network=dstack-gpu-data-net-$N \
        --region=$REGION \
        --range=192.168.$N.0/24

    gcloud compute firewall-rules create dstack-gpu-data-internal-$N \
      --network=dstack-gpu-data-net-$N \
      --action=ALLOW \
      --rules=tcp:0-65535,udp:0-65535,icmp \
      --source-ranges=192.168.0.0/16
    done
    ```

??? info "Create Service Account"
    Create a VM service account that allows VMs to access the `pkg.dev` registry:

    ```shell
    PROJECT_ID=$(gcloud config get-value project)
    gcloud iam service-accounts create a3cluster-sa \
        --display-name "Service Account for pulling GCR images"
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:a3cluster-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/artifactregistry.reader"
    ```

## Create A3 High fleet

Once you've configured the `gcp` backend, create the fleet configuration:

<div editor-title="fleet.dstack.yml">
```yaml
type: fleet
name: a3high-cluster
nodes: 2
placement: cluster
instance_types:
  - a3-highgpu-8g
spot_policy: auto
```
</div>

and apply the configuration:

<div class="termy">

```shell
$ dstack apply -f fleet.dstack.yml
 Project        main                           
 User           admin                          
 Configuration  fleet.dstack.yml               
 Type           fleet                          
 Fleet type     cloud                          
 Nodes          2                              
 Placement      cluster                        
 Resources      2..xCPU, 8GB.., 100GB.. (disk) 
 Spot policy    auto                           

 #  BACKEND  REGION        INSTANCE       RESOURCES           SPOT  PRICE      
 1  gcp      europe-west4  a3-highgpu-8g  208xCPU, 1872GB,    yes   $20.5688   
                                          8xH100 (80GB),                       
                                          100.0GB (disk)                       
 2  gcp      europe-west4  a3-highgpu-8g  208xCPU, 1872GB,    no    $58.5419   
                                          8xH100 (80GB),                       
                                          100.0GB (disk)                       

Fleet a3high-cluster does not exist yet.
Create the fleet? [y/n]: y

Provisioning...
---> 100%                    
```

</div>

`dstack` will provision two A3 High nodes with GPUDirect-TCPX configured.

## Run NCCL Tests with GPUDirect-TCPX support

Once the nodes are provisioned, let's test the network by running NCCL Tests:

<div class="termy">

```shell 
$ dstack apply -f examples/misc/a3high-clusters/nccl-tests.dstack.yml 

nccl-tests provisioning completed (running)
nThread 1 nGpus 1 minBytes 8388608 maxBytes 8589934592 step: 2(factor) warmup iters: 5 iters: 200 agg iters: 1 validation: 0 graph: 0

                                                              out-of-place                       in-place          
       size         count      type   redop    root     time   algbw   busbw #wrong     time   algbw   busbw #wrong
        (B)    (elements)                               (us)  (GB/s)  (GB/s)            (us)  (GB/s)  (GB/s)       
     8388608        131072     float    none      -1    784.9   10.69   10.02      0    775.9   10.81   10.14      0
    16777216        262144     float    none      -1   1010.3   16.61   15.57      0    999.3   16.79   15.74      0
    33554432        524288     float    none      -1   1161.6   28.89   27.08      0   1152.9   29.10   27.28      0
    67108864       1048576     float    none      -1   1432.6   46.84   43.92      0   1437.8   46.67   43.76      0
   134217728       2097152     float    none      -1   2516.9   53.33   49.99      0   2491.7   53.87   50.50      0
   268435456       4194304     float    none      -1   5066.8   52.98   49.67      0   5131.4   52.31   49.04      0
   536870912       8388608     float    none      -1    10028   53.54   50.19      0    10149   52.90   49.60      0
  1073741824      16777216     float    none      -1    20431   52.55   49.27      0    20214   53.12   49.80      0
  2147483648      33554432     float    none      -1    40254   53.35   50.01      0    39923   53.79   50.43      0
  4294967296      67108864     float    none      -1    80896   53.09   49.77      0    78875   54.45   51.05      0
  8589934592     134217728     float    none      -1   160505   53.52   50.17      0   160117   53.65   50.29      0
Out of bounds values : 0 OK
Avg bus bandwidth    : 40.6043

Done
```

</div>

## Run NCCL workloads with GPUDirect-TCPX support

To take full advantage of GPUDirect-TCPX in your workloads, you need properly set up the [NCCL environment variables](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot#environment-variables-nccl).
This can be done with the following commands in your run configuration:

<div editor-title="task.dstack.yml">

```yaml
type: task
nodes: 2
commands:
  - |
    export NCCL_DEBUG=INFO
    NCCL_LIB_DIR="/usr/local/tcpx/lib64"
    export LD_LIBRARY_PATH="${NCCL_LIB_DIR}:${LD_LIBRARY_PATH}"
    export NCCL_SOCKET_IFNAME=eth0
    export NCCL_CROSS_NIC=0
    export NCCL_ALGO=Ring
    export NCCL_PROTO=Simple
    export NCCL_NSOCKS_PERTHREAD=4
    export NCCL_SOCKET_NTHREADS=1
    export NCCL_NET_GDR_LEVEL=PIX
    export NCCL_P2P_PXN_LEVEL=0
    export NCCL_GPUDIRECTTCPX_SOCKET_IFNAME=eth1,eth2,eth3,eth4
    export NCCL_GPUDIRECTTCPX_CTRL_DEV=eth0
    export NCCL_DYNAMIC_CHUNK_SIZE=524288
    export NCCL_P2P_NET_CHUNKSIZE=524288
    export NCCL_P2P_PCI_CHUNKSIZE=524288
    export NCCL_P2P_NVL_CHUNKSIZE=1048576
    export NCCL_BUFFSIZE=4194304
    export NCCL_GPUDIRECTTCPX_TX_BINDINGS="eth1:8-21,112-125;eth2:8-21,112-125;eth3:60-73,164-177;eth4:60-73,164-177"
    export NCCL_GPUDIRECTTCPX_RX_BINDINGS="eth1:22-35,126-139;eth2:22-35,126-139;eth3:74-87,178-191;eth4:74-87,178-191"
    export NCCL_GPUDIRECTTCPX_PROGRAM_FLOW_STEERING_WAIT_MICROS=50000
    export NCCL_GPUDIRECTTCPX_UNIX_CLIENT_PREFIX="/run/tcpx"
    # run NCCL
resources:
  # Allocate some shared memory for NCCL
  shm_size: 16GB
```

</div>

!!! info "Future plans"
    We're working on improving support for A3 High and A3 Edge by pre-building `dstack` VM image optimized for GPUDirect-TCPX instead of relying on the COS image used now, similar to the `dstack` support for A3 Mega. This will make configuration easier, reduce provisioning time, and improve performance. We're in contact with GCP on this issue.

## Source code

The source code for this example can be found in 
[`examples/distributed-training/a3high-clusters` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/distributed-training/a3high-clusters).
