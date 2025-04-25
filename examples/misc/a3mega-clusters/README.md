# GCP A3 Mega clusters

This example shows how to set up a GCP A3 Mega cluster with [GPUDirect-TCPXO](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot)
optimized NCCL communication and run [NCCL Tests](https://github.com/NVIDIA/nccl-tests) on it using `dstack`.

## Overview

GCP's A3 Mega instances are 8xH100 VMs that have 1800Gbps maximum network bandwidth,
which is the best among GCP H100 instances. To get that network performance, you need
to set up GPUDirect-TCPXO – the GCP technology for GPU RDMA over TCP. This involves:

* Setting up eight extra data NICs on every node, each NIC in a separate VPC.
* Building a VM image with the GPUDirect-TCPXO support.
* Launching an RXDM service container.
* Installing the GPUDirect-TCPXO NCCL plugin.

`dstack` hides most of the setup complexity and provides optimized A3 Mega clusters out-of-the-box.

## Configure GCP backend

First configure the `gcp` backend for the GPUDirect-TCPXO support.
You need to specify eight `extra_vpcs` to use for data NICs:

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
        - dstack-gpu-data-net-5
        - dstack-gpu-data-net-6
        - dstack-gpu-data-net-7
        - dstack-gpu-data-net-8
      regions: [europe-west4]
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

    for N in $(seq 1 8); do
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

## Create A3 Mega fleet

Once you've configured the `gcp` backend, create the fleet configuration:

<div editor-title="fleet.dstack.yml">
```yaml
type: fleet
name: a3mega-cluster
nodes: 2
placement: cluster
instance_types:
  - a3-megagpu-8g
spot_policy: auto
```
</div>

and apply the configuration:

<div class="termy">

```shell
$ dstack apply -f examples/misc/a3mega-clusters/fleet.dstack.yml
 Project        main                           
 User           admin                          
 Configuration  examples/misc/a3mega-clusters/fleet.dstack.yml 
 Type           fleet                          
 Fleet type     cloud                          
 Nodes          2                              
 Placement      cluster                        
 Resources      2..xCPU, 8GB.., 100GB.. (disk) 
 Spot policy    auto                           

 #  BACKEND  REGION        INSTANCE       RESOURCES              SPOT  PRICE      
 1  gcp      europe-west4  a3-megagpu-8g  208xCPU, 1872GB,       yes   $22.1525   
                                          8xH100 (80GB),                          
                                          100.0GB (disk)                          
 2  gcp      europe-west4  a3-megagpu-8g  208xCPU, 1872GB,       no    $64.2718   
                                          8xH100 (80GB),                          
                                          100.0GB (disk)                          

Fleet a3mega-cluster does not exist yet.
Create the fleet? [y/n]: y

Provisioning...
---> 100%                    
```

</div>

`dstack` will provision two A3 Mega nodes with GPUDirect-TCPXO configured.

## Run NCCL Tests with GPUDirect-TCPXO support

Once the nodes are provisioned, let's test the network by running NCCL Tests:

<div class="termy">

```shell 
$ dstack apply -f examples/misc/a3mega-clusters/nccl-tests.dstack.yml 

nccl-tests provisioning completed (running)
nThread 1 nGpus 1 minBytes 8388608 maxBytes 8589934592 step: 2(factor) warmup iters: 5 iters: 200 agg iters: 1 validation: 0 graph: 0

                                                             out-of-place                       in-place          
      size         count      type   redop    root     time   algbw   busbw #wrong     time   algbw   busbw #wrong
       (B)    (elements)                               (us)  (GB/s)  (GB/s)            (us)  (GB/s)  (GB/s)       
     8388608        131072     float    none      -1    166.6   50.34   47.19    N/A    164.1   51.11   47.92    N/A
    16777216        262144     float    none      -1    204.6   82.01   76.89    N/A    203.8   82.30   77.16    N/A
    33554432        524288     float    none      -1    284.0  118.17  110.78    N/A    281.7  119.12  111.67    N/A
    67108864       1048576     float    none      -1    447.4  150.00  140.62    N/A    443.5  151.31  141.86    N/A
   134217728       2097152     float    none      -1    808.3  166.05  155.67    N/A    801.9  167.38  156.92    N/A
   268435456       4194304     float    none      -1   1522.1  176.36  165.34    N/A   1518.7  176.76  165.71    N/A
   536870912       8388608     float    none      -1   2892.3  185.62  174.02    N/A   2894.4  185.49  173.89    N/A
  1073741824      16777216     float    none      -1   5532.7  194.07  181.94    N/A   5530.7  194.14  182.01    N/A
  2147483648      33554432     float    none      -1    10863  197.69  185.34    N/A    10837  198.17  185.78    N/A
  4294967296      67108864     float    none      -1    21481  199.94  187.45    N/A    21466  200.08  187.58    N/A
  8589934592     134217728     float    none      -1    42713  201.11  188.54    N/A    42701  201.16  188.59    N/A
Out of bounds values : 0 OK
Avg bus bandwidth    : 146.948 

Done
```

The networking bandwidth should be close to the maximum bandwidth supported by GCP.

</div>

## Run NCCL workloads with GPUDirect-TCPXO support

To take full advantage of GPUDirect-TCPXO in your workloads, you need properly set up the [NCCL environment variables](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot#environment-variables-nccl).
This can be done with the following commands in your run configuration:

<div editor-title="task.dstack.yml">

```yaml
type: task
nodes: 2
commands:
  - |
    NCCL_LIB_DIR="/var/lib/tcpxo/lib64"
    source ${NCCL_LIB_DIR}/nccl-env-profile-ll128.sh
    export NCCL_FASTRAK_CTRL_DEV=enp0s12
    export NCCL_FASTRAK_IFNAME=enp6s0,enp7s0,enp13s0,enp14s0,enp134s0,enp135s0,enp141s0,enp142s0
    export NCCL_SOCKET_IFNAME=enp0s12
    export NCCL_FASTRAK_LLCM_DEVICE_DIRECTORY="/dev/aperture_devices"
    export LD_LIBRARY_PATH="${NCCL_LIB_DIR}:${LD_LIBRARY_PATH}"
    # run NCCL
resources:
  # Allocate some shared memory for NCCL
  shm_size: 16GB
```

</div>

## Source code

The source code for this example can be found in 
[`examples/misc/a3mega-clusters` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/a3mega-clusters).
