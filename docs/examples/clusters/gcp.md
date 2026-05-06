---
title: GCP
description: Creating and using GPU clusters on GCP with GPUDirect-TCPX and RoCE support
---

# GCP

This example shows how to create and use clusters on GCP.

`dstack` supports the following instance types:

| Instance type | GPU    | Maximum bandwidth | Fabric                                                                                                           |
| ------------- | ------ | ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| **A3 Edge**   | H100:8 | 0.8 Tbps          | [GPUDirect-TCPX](https://cloud.google.com/compute/docs/gpus/gpudirect)                                           |
| **A3 High**   | H100:8 | 1 Tbps            | [GPUDirect-TCPX](https://cloud.google.com/compute/docs/gpus/gpudirect)                                           |
| **A3 Mega**   | H100:8 | 1.8 Tbps          | [GPUDirect-TCPXO](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot) |
| **A4**        | B200:8 | 3.2 Tbps          | RoCE                                                                                                             |

## Configure the backend

Despite hiding most of the complexity, `dstack` still requires instance-specific backend configuration:

=== "A4"
    A4 requires one `extra_vpcs` for inter-node traffic (regular VPC, one subnet) and one `roce_vpcs` for GPU-to-GPU communication (RoCE profile, eight subnets).

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
        - type: gcp
          # Specify your GCP project ID
          project_id: <project id>

          extra_vpcs: [dstack-gvnic-net-1]
          roce_vpcs: [dstack-mrdma]

          # Specify the regions you intend to use
          regions: [us-west2]

          creds:
            type: default
    ```

    </div>

    <h4>Create extra and RoCE VPCs</h4>
    
    See GCP's [RoCE network setup guide](https://cloud.google.com/ai-hypercomputer/docs/create/create-vm#setup-network) for the commands to create
    VPCs and filewall rules. 
    
    Ensure VPCs allow internal traffic between nodes for MPI/NCCL to function.

=== "A3 Mega"
    A3 Edge/High require at least 4 `extra_vpcs` for data NICs.

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
        - type: gcp
          # Specify your GCP project ID
          project_id: <project id>

          extra_vpcs:
            - dstack-gpu-data-net-1
            - dstack-gpu-data-net-2
            - dstack-gpu-data-net-3
            - dstack-gpu-data-net-4
            - dstack-gpu-data-net-5
            - dstack-gpu-data-net-6
            - dstack-gpu-data-net-7
            - dstack-gpu-data-net-8
          
          # Specify the regions you intend to use
          regions: [europe-west4]
          
          creds:
            type: default
    ```

    </div>

    <h4>Create extra VPCs</h4>

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

=== "A3 High/Edge"
    A3 Edge/High require at least 4 `extra_vpcs` for data NICs and a `vm_service_account` authorized to pull GPUDirect Docker images.

    <div editor-title="~/.dstack/server/config.yml">

    ```yaml
    projects:
    - name: main
      backends:
        - type: gcp
          # Specify your GCP project ID
          project_id: <project id>

          extra_vpcs:
            - dstack-gpu-data-net-1
            - dstack-gpu-data-net-2
            - dstack-gpu-data-net-3
            - dstack-gpu-data-net-4

          # Specify the regions you intend to use
          regions: [europe-west4]

          # Specify your GCP project ID
          vm_service_account: a3cluster-sa@$<project id>.iam.gserviceaccount.com

          creds:
            type: default
    ```

    </div>

    <h4>Create extra VPCs</h4>

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

    <h4>Create a service account</h4>

    Create a VM service account that allows VMs to access the `pkg.dev` registry:

    ```shell
    PROJECT_ID=$(gcloud config get-value project)

    gcloud iam service-accounts create a3cluster-sa \
        --display-name "Service Account for pulling GCR images"

    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:a3cluster-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
        --role="roles/artifactregistry.reader"
    ```

!!! info "Default VPC"
    If you set a non-default `vpc_name` in the backend configuration, ensure it allows all inter-node traffic. This is required for MPI and NCCL. The default VPC already allows this.

## Create a fleet

Once you've configured the `gcp` backend, create the fleet configuration:

=== "A4"

    <div editor-title="a4-fleet.dstack.yml">

    ```yaml
    type: fleet
    name: a4-fleet

    placement: cluster
    # Can be a range on a fixed number
    nodes: 2

    # Specify the zone where you have configured the RoCE VPC
    availability_zones: [us-west2-c]

    backends: [gcp]

    # Uncomment to allow spot instances 
    #spot_policy: auto

    resources:
      gpu: B200:8
    ```

    </div>

    Then apply it with `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f a4-fleet.dstack.yml

    Provisioning...
    ---> 100%

    FLEET     INSTANCE  BACKEND         GPU                  PRICE    STATUS  CREATED
    a4-fleet  0         gcp (us-west2)  B200:180GB:8 (spot)  $51.552  idle    9 mins ago
              1         gcp (us-west2)  B200:180GB:8 (spot)  $51.552  idle    9 mins ago
    ```

    </div>

=== "A3 Mega"

    <div editor-title="fleet.dstack.yml">

    ```yaml
        type: fleet
        name: a3mega-fleet
        
        placement: cluster
        # Can be a range on a fixed number
        nodes: 2
        
        instance_types:
          - a3-megagpu-8g
        
        # Uncomment to allow spot instances 
        #spot_policy: auto
    ```
    </div>

    Pass the configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f a3mega-fleet.dstack.yml                

    FLEET         INSTANCE  BACKEND             GPU          PRICE            STATUS  CREATED
    a3mega-fleet  1         gcp (europe-west4)  H100:80GB:8  $22.1525 (spot)  idle    9 mins ago
    a3mega-fleet  2         gcp (europe-west4)  H100:80GB:8  $64.2718         idle    9 mins ago

    Create the fleet? [y/n]: y

    Provisioning...
    ---> 100%
    ```

    </div>

=== "A3 High/Edge"

    <div editor-title="a3high-fleet.dstack.yml">

    ```yaml
    type: fleet
    name: a3high-fleet

    placement: cluster
    nodes: 2

    instance_types:
      - a3-highgpu-8g
    
    # Uncomment to allow spot instances 
    #spot_policy: auto
    ```

    </div>

    Pass the configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f a3high-fleet.dstack.yml
                   
    FLEET         INSTANCE  BACKEND             GPU          PRICE            STATUS  CREATED
    a3mega-fleet  1         gcp (europe-west4)  H100:80GB:8  $20.5688 (spot)  idle    9 mins ago
    a3mega-fleet  2         gcp (europe-west4)  H100:80GB:8  $58.5419         idle    9 mins ago

    Create the fleet? [y/n]: y

    Provisioning...
    ---> 100%                    
    ```

    </div>

Once the fleet is created, you can run distributed tasks, in addition to dev environments, services, and regular tasks.

## Run tasks

### NCCL tests

Use a distributed task that runs NCCL tests to validate cluster network bandwidth.

=== "A4"
    Pass the configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f nccl-tests.dstack.yml

    Provisioning...
    ---> 100%
    
    nccl-tests provisioning completed (running)
    nThread 1 nGpus 1 minBytes 8 maxBytes 8589934592 step: 2(factor) warmup iters: 5 iters: 20 agg iters: 1 validation: 1 graph: 0
          size         count      type   redop    root     time   algbw   busbw  wrong     time   algbw   busbw  wrong
           (B)    (elements)                               (us)  (GB/s)  (GB/s)            (us)  (GB/s)  (GB/s)       
       8388608       2097152     float     sum      -1    156.9   53.47  100.25      0    167.6   50.06   93.86      0
      16777216       4194304     float     sum      -1    196.3   85.49  160.29      0    206.2   81.37  152.57      0
      33554432       8388608     float     sum      -1    258.5  129.82  243.42      0    261.8  128.18  240.33      0
      67108864      16777216     float     sum      -1    369.4  181.69  340.67      0    371.2  180.79  338.98      0
     134217728      33554432     float     sum      -1    638.5  210.22  394.17      0    587.2  228.57  428.56      0
     268435456      67108864     float     sum      -1    940.3  285.49  535.29      0    950.7  282.36  529.43      0
     536870912     134217728     float     sum      -1   1695.2  316.70  593.81      0   1666.9  322.08  603.89      0
    1073741824     268435456     float     sum      -1   3229.9  332.44  623.33      0   3201.8  335.35  628.78      0
    2147483648     536870912     float     sum      -1   6107.7  351.61  659.26      0   6157.1  348.78  653.97      0
    4294967296    1073741824     float     sum      -1    11952  359.36  673.79      0    11942  359.65  674.34      0
    8589934592    2147483648     float     sum      -1    23563  364.55  683.52      0    23702  362.42  679.54      0
    Out of bounds values : 0 OK
    Avg bus bandwidth    : 165.789
    ```

    </div>

=== "A3 Mega"

    <div editor-title="nccl-tests.dstack.yml">

    ```yaml
    type: task
    name: nccl-tests
    nodes: 2
    image: nvcr.io/nvidia/pytorch:24.04-py3
    entrypoint: "bash -c" # Need to use bash instead of default dash for nccl-env-profile.sh
    commands:
      - |
        # Setup TCPXO NCCL env variables
        NCCL_LIB_DIR="/var/lib/tcpxo/lib64"
        source ${NCCL_LIB_DIR}/nccl-env-profile-ll128.sh
        export NCCL_FASTRAK_CTRL_DEV=enp0s12
        export NCCL_FASTRAK_IFNAME=enp6s0,enp7s0,enp13s0,enp14s0,enp134s0,enp135s0,enp141s0,enp142s0
        export NCCL_SOCKET_IFNAME=enp0s12
        export NCCL_FASTRAK_LLCM_DEVICE_DIRECTORY="/dev/aperture_devices"
        export LD_LIBRARY_PATH="${NCCL_LIB_DIR}:${LD_LIBRARY_PATH}"
        # Build NCCL Tests
        git clone https://github.com/NVIDIA/nccl-tests.git
        cd nccl-tests
        MPI=1 CC=mpicc CXX=mpicxx make -j
        cd build
        # We use FIFO for inter-node communication
        FIFO=/tmp/dstack_job
        if [ ${DSTACK_NODE_RANK} -eq 0 ]; then
          sleep 10
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
            --mca btl tcp,self --mca btl_tcp_if_exclude lo,docker0 \
            $(env | awk -F= '{print "-x", $1}' | xargs) \
            ./all_gather_perf -b 8M -e 8G -f 2 -g 1 -w 5 --iters 200 -c 0;
          # Notify nodes the job is done
          ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 sh -c "echo done > ${FIFO}"
        else
          mkfifo ${FIFO}
          # Wait for a message from the first node
          cat ${FIFO}
        fi
    spot_policy: auto
    resources:
      shm_size: 16GB
    ```

    </div>

    Pass the configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f nccl-tests.dstack.yml

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
    ```

    </div>

=== "A3 High/Edge"

    <div editor-title="nccl-tests.dstack.yml">

    ```yaml
    type: task
    name: nccl-tests
    nodes: 2
    image: us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpx/nccl-plugin-gpudirecttcpx
    commands:
      - |
        export NCCL_DEBUG=INFO
        export LD_LIBRARY_PATH=/usr/local/tcpx/lib64:$LD_LIBRARY_PATH
        # We use FIFO for inter-node communication
        FIFO=/tmp/dstack_job
        if [ ${DSTACK_NODE_RANK} -eq 0 ]; then
          mkdir -p /scripts/hostfiles2
          : > /scripts/hostfiles2/hostfile8
          for ip in ${DSTACK_NODES_IPS}; do
            echo "${ip} slots=${DSTACK_GPUS_PER_NODE}" >> /scripts/hostfiles2/hostfile8
          done
          MPIRUN='mpirun --allow-run-as-root --hostfile /scripts/hostfiles2/hostfile8'
          # Wait for other nodes
          while true; do
            if ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 true >/dev/null 2>&1; then
              break
            fi
            echo 'Waiting for nodes...'
            sleep 5
          done
          # Run NCCL Tests
          NCCL_GPUDIRECTTCPX_FORCE_ACK=0 /scripts/run-allgather.sh 8 eth1,eth2,eth3,eth4 8M 8GB 2
          # Notify nodes the job is done
          ${MPIRUN} -n ${DSTACK_NODES_NUM} -N 1 sh -c "echo done > ${FIFO}"
        else
          mkfifo ${FIFO}
          # Wait for a message from the first node
          cat ${FIFO}
        fi
    spot_policy: auto
    resources:
      shm_size: 16GB
    ```

    </div>

    Pass the configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f nccl-tests.dstack.yml

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
    ```

    </div>

### Distributed training

=== "A4"
    You can use the standard [distributed task](../../docs/concepts/tasks.md#distributed-tasks) example to run distributed training on A4 instances.

=== "A3 Mega"
    You can use the standard [distributed task](../../docs/concepts/tasks.md#distributed-tasks) example to run distributed training on A3 Mega instances. To enable GPUDirect-TCPX, make sure the required [NCCL environment variables](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot#environment-variables-nccl) are properly set, for example by adding the following commands at the beginning:

    ```shell
    # ...

    commands: 
    - | 
      NCCL_LIB_DIR="/var/lib/tcpxo/lib64"
      source ${NCCL_LIB_DIR}/nccl-env-profile-ll128.sh
      export NCCL_FASTRAK_CTRL_DEV=enp0s12
      export NCCL_FASTRAK_IFNAME=enp6s0,enp7s0,enp13s0,enp14s0,enp134s0,enp135s0,enp141s0,enp142s0
      export NCCL_SOCKET_IFNAME=enp0s12
      export NCCL_FASTRAK_LLCM_DEVICE_DIRECTORY="/dev/aperture_devices"
      export LD_LIBRARY_PATH="${NCCL_LIB_DIR}:${LD_LIBRARY_PATH}"
    
    # ...
    ```

=== "A3 High/Edge"
    You can use the standard [distributed task](../../docs/concepts/tasks.md#distributed-tasks) example to run distributed training on A3 High/Edge instances. To enable GPUDirect-TCPX0, make sure the required [NCCL environment variables](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot#environment-variables-nccl) are properly set, for example by adding the following commands at the beginning:

    ```shell
    # ...

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
    
    # ...
    ```

In addition to distributed training, you can of course run regular tasks, dev environments, and services.

## What's new

1. Learn about [dev environments](../../docs/concepts/dev-environments.md), [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md)
2. Read about [cluster placement](../../docs/concepts/fleets.md#cluster-placement)
3. Check GCP's docs on using [A4](https://docs.cloud.google.com/compute/docs/gpus/create-gpu-vm-a3u-a4), and [A3 Mega/High/Edge](https://docs.cloud.google.com/compute/docs/gpus/gpudirect) instances
