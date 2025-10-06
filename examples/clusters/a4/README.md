# GCP A4

This example shows how to set up a GCP A4 cluster with optimized RoCE networking and run NCCL Tests on it using `dstack`.

GCP A4 instances provide eight NVIDIA B200 GPUs per VM, each with 180GB memory. These instances also have eight NVIDIA ConnectX-7 (CX-7) NICs that utilize RDMA over Converged Ethernet (RoCE) networking, making them ideal for large-scale distributed deep learning.

## Configure the GCP backend

First, configure the `gcp` backend for A4 RoCE support. Specify one VPC in `extra_vpcs` for general traffic between nodes (in addition to the main VPC), and one VPC in `roce_vpcs` for GPU-to-GPU communication.

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: gcp
    project_id: my-project
    creds:
      type: default
    vpc_name: my-vpc-0  # Main VPC (1 subnet, omit to use the default VPC)
    extra_vpcs:
    - my-vpc-1          # Extra VPC (1 subnet)
    roce_vpcs:
    - my-vpc-mrdma      # RoCE VPC (8 subnets, RoCE profile)
```

</div>

!!! info "RoCE VPC setup"
    The VPC listed in `roce_vpcs` must be created with the RoCE profile and have **eight subnets** (one per GPU). Follow [GCP's RoCE setup guide](https://cloud.google.com/ai-hypercomputer/docs/create/create-vm#setup-network) for details.

!!! info "Firewall rules"
    Ensure all VPCs allow internal traffic between nodes for MPI/NCCL to function.

## Create a fleet

Define your fleet configuration:

<div editor-title="examples/clusters/a4/fleet.dstack.yml">

```yaml
type: fleet
name: a4-cluster

nodes: 2
placement: cluster

# Specify the zone where you have configured the RoCE VPC
availability_zones: [us-west2-c]
backends: [gcp]
spot_policy: auto

resources:
  gpu: B200:8
```

</div>

Then apply it with `dstack apply`:

<div class="termy">

```shell
$ dstack apply -f examples/clusters/a4/fleet.dstack.yml

Provisioning...
---> 100%

 FLEET       INSTANCE  BACKEND         GPU                  PRICE    STATUS  CREATED
 a4-cluster  0         gcp (us-west2)  B200:180GB:8 (spot)  $51.552  idle    9 mins ago
             1         gcp (us-west2)  B200:180GB:8 (spot)  $51.552  idle    9 mins ago
```

</div>

`dstack` will provision the instances and set up ten network interfaces on each instance:

- 1 regular network interface in the main VPC (`vpc_name`)
- 1 regular interface in an extra VPC (`extra_vpcs`)
- 8 RoCE-enabled interfaces in a dedicated VPC (`roce_vpcs`)

!!! info "Spot instances"
    Currently, the `gcp` backend supports only A4 spot instances.

## Run NCCL tests

To validate networking and GPU performance, you can run [NCCL tests](https://dstack.ai/examples/clusters/nccl-tests/):

<div class="termy">

```shell
$ dstack apply -f examples/clusters/nccl-tests/.dstack.yml

Provisioning...
---> 100%

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

!!! info "What's next"
    1. Learn more about [distributed tasks](https://dstack.ai/docs/concepts/tasks#distributed-tasks) 
    2. Check [dev environments](https://dstack.ai/docs/concepts/dev-environments),
       [services](https://dstack.ai/docs/concepts/services), and [fleets](https://dstack.ai/docs/concepts/fleets)
    3. Read the [Clusters](https://dstack.ai/docs/guides/clusters) guide
