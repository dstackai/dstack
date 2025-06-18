# Clusters

A cluster is a [fleet](../concepts/fleets.md) with its `placement` set to `cluster`. This configuration ensures that the instances within the fleet are interconnected, enabling fast inter-node communication—crucial for tasks such as efficient distributed training.

## Fleets

Ensure a fleet is created before you run any distributed task. This can be either an SSH fleet or a cloud fleet.

### SSH fleets

[SSH fleets](../concepts/fleets.md#ssh) can be used to create a fleet out of existing baremetals or VMs, e.g. if they are already pre-provisioned, or set up on-premises.

> For SSH fleets, fast interconnect is supported provided that the hosts are pre-configured with the appropriate interconnect drivers.

### Cloud fleets

[Cloud fleets](../concepts/fleets.md#cloud) allow to provision interconnected clusters across supported backends.
For cloud fleets, fast interconnect is currently supported only on the `aws`, `gcp`, and `nebius` backends.

=== "AWS"
    When you create a cloud fleet with AWS, [Elastic Fabric Adapter :material-arrow-top-right-thin:{ .external }](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa.html){:target="_blank"} networking is automatically configured if it’s supported for the corresponding instance type.
    
    !!! info "Backend configuration"    
        Note, EFA requires the `public_ips` to be set to `false` in the `aws` backend configuration.
        Refer to the [EFA](../../examples/clusters/efa/index.md) example for more details.

=== "GCP"
    When you create a cloud fleet with GCP, for the A3 Mega and A3 High instance types, [GPUDirect-TCPXO and GPUDirect-TCPX :material-arrow-top-right-thin:{ .external }](https://cloud.google.com/kubernetes-engine/docs/how-to/gpu-bandwidth-gpudirect-tcpx-autopilot){:target="_blank"} networking is automatically configured.

    !!! info "Backend configuration"    
        Note, GPUDirect-TCPXO and GPUDirect-TCPX require `extra_vpcs` to be configured  in the `gcp` backend configuration.
        Refer to the [A3 Mega](../../examples/clusters/a3mega/index.md) and 
        [A3 High](../../examples/clusters/a3high/index.md) examples for more details.

=== "Nebius"
    When you create a cloud fleet with Nebius, [InfiniBand :material-arrow-top-right-thin:{ .external }](https://docs.nebius.com/compute/clusters/gpu){:target="_blank"} networking is automatically configured if it’s supported for the corresponding instance type.

> To request fast interconnect support for a other backends,
file an [issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues){:target="_ blank"}. 

## Distributed tasks

A distributed task is a task with `nodes` set to a value greater than `2`. In this case, `dstack` first ensures a 
suitable fleet is available, then selects the master node (to obtain its IP) and finally runs jobs on each node.

Within the task's `commands`, it's possible to use `DSTACK_MASTER_NODE_IP`, `DSTACK_NODES_IPS`, `DSTACK_NODE_RANK`, and other
[system environment variables](../concepts/tasks.md#system-environment-variables) for inter-node communication.

??? info "MPI"
    If want to use MPI, you can set `startup_order` to `workers-first` and `stop_criteria` to `master-done`, and use `DSTACK_MPI_HOSTFILE`.
    See the [NCCL](../../examples/clusters/nccl-tests/index.md) or [RCCL](../../examples/clusters/rccl-tests/index.md) examples.

!!! info "Retry policy"
    By default, if any of the nodes fails, `dstack` terminates the entire run. Configure a [retry policy](../concepts/tasks.md#retry-policy) to  restart the run if any node fails.

Refer to [distributed tasks](../concepts/tasks.md#distributed-tasks) for an example.

## NCCL/RCCL tests

To test the interconnect of a created fleet, ensure you run [NCCL](../../examples/clusters/nccl-tests/index.md) 
(for NVIDIA) or [RCCL](../../examples/clusters/rccl-tests/index.md) (for AMD) tests using MPI.

## Volumes

### Instance volumes

[Instance volumes](../concepts/volumes.md#instance) enable mounting any folder from the host into the container, allowing data persistence during distributed tasks.

Instance volumes can be used to mount:

* Regular folders (data persists only while the fleet exists)
* Folders that are mounts of shared filesystems (e.g., manually mounted shared filesystems).

### Network volumes
    
Currently, no backend supports multi-attach [network volumes](../concepts/volumes.md#network) for distributed tasks. However, single-attach volumes can be used by leveraging volume name [interpolation syntax](../concepts/volumes.md#distributed-tasks). This approach mounts a separate single-attach volume to each node.

!!! info "What's next?"
    1. Read about [distributed tasks](../concepts/tasks.md#distributed-tasks), [fleets](../concepts/fleets.md), and [volumes](../concepts/volumes.md)
    2. Browse the [Clusters](../../examples.md#clusters) and [Distributed training](../../examples.md#distributed-training) examples
    
