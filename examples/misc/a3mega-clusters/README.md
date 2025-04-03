# A3 Mega GCP clusters

This example shows how to set up an A3 Mega GCP cluster with [GPUDirect-TCPXO](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot)
optimized NCCL communication and run [NCCL Tests](https://github.com/NVIDIA/nccl-tests) on it using `dstack`.

## Overview

GCP's A3 Mega instances are 8xH100 VMs that have 1800Gbps maximum network bandwidth,
which is the best among H100 GCP instances. To get that network performance, you need
to set up GPUDirect-TCPXO – the GCP technology for GPU RDMA over TCP. This involves:

* Setting up eight extra data NICs on every node, each NIC in a separate VPC.
* Building a VM image with the GPUDirect-TCPXO support.
* Launching an RXDM service container.
* Installing the GPUDirect-TCPXO NCCL plugin.

`dstack` hides most of the setup complexity and provides optimized A3 Mega GCP clusters out-of-the-box.

## Configure GCP backend

First configure the `gcp` backend for the GPUDirect-TCPXO support.
You need to specify eight `extra_vpcs` to use for data NICs.
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
        - dstack-gpu-data-net-5
        - dstack-gpu-data-net-6
        - dstack-gpu-data-net-7
        - dstack-gpu-data-net-8
      regions: [europe-west4]
      vm_service_account: a3mega-sa@$MYPROJECT.iam.gserviceaccount.com # Replace $MYPROJECT
      creds:
        type: default
```

</div>

??? info "Create extra VPCs"
    Create the VPC networks for GPUDirect in your project, each with a subnet and a firewall rule. Choose the GPUDirect-TCPX tab for A3 High machine types, or choose the GPUDirect-TCPXO tab for A3 Mega machine types, then complete the following instructions:
    
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

??? info "Create Service Account"
    Create a VM service account that allows VMs to access the `pkg.dev` registry:
    
    ```shell
    PROJECT_ID=$(gcloud config get-value project)

    gcloud iam service-accounts create a3mega-sa \
        --display-name "Service Account for pulling GCR images"

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:a3mega-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/artifactregistry.reader"
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
     8388608        131072     float    none      -1    394.2   21.28   19.95    N/A    392.7   21.36   20.03    N/A
    16777216        262144     float    none      -1    437.8   38.32   35.92    N/A    434.1   38.65   36.24    N/A
    33554432        524288     float    none      -1    479.5   69.98   65.61    N/A    479.9   69.92   65.55    N/A
    67108864       1048576     float    none      -1    755.8   88.79   83.24    N/A    771.9   86.94   81.51    N/A
   134217728       2097152     float    none      -1   1125.3  119.27  111.81    N/A   1121.8  119.64  112.16    N/A
   268435456       4194304     float    none      -1   1741.3  154.16  144.53    N/A   1742.2  154.08  144.45    N/A
   536870912       8388608     float    none      -1   2854.9  188.05  176.30    N/A   2869.8  187.08  175.38    N/A
  1073741824      16777216     float    none      -1   5536.1  193.95  181.83    N/A   5528.8  194.21  182.07    N/A
  2147483648      33554432     float    none      -1    10853  197.88  185.51    N/A    10830  198.29  185.90    N/A
  4294967296      67108864     float    none      -1    21491  199.85  187.36    N/A    21466  200.09  187.58    N/A
  8589934592     134217728     float    none      -1    42770  200.84  188.29    N/A    42752  200.93  188.37    N/A
Out of bounds values : 0 OK
Avg bus bandwidth    : 125.436 

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
    source ${NCCL_LIB_DIR}/nccl-env-profile.sh
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
