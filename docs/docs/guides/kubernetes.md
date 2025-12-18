# Kubernetes

The [kubernetes](../concepts/backends.md#kubernetes) backend enables `dstack` to run [dev environments](/docs/concepts/dev-environments), [tasks](/docs/concepts/tasks), and [services](/docs/concepts/services) directly on existing Kubernetes clusters.

If your GPUs are already deployed on Kubernetes and your team relies on its ecosystem and tooling, use this backend to integrate `dstack` with your clusters.

> If Kubernetes is not required, you can run `dstack` on clouds or on-prem clusters without Kubernetes by using [VM-based](../concepts/backends.md#vm-based), [container-based](../concepts/backends.md#container-based), or [on-prem](../concepts/backends.md#on-prem) backends.

## Setting up the backend

To use the `kubernetes` backend with `dstack`, you need to configure it with the path to the kubeconfig file, the IP address of any node in the cluster, and the port that `dstack` will use for proxying SSH traffic. 
This configuration is defined in the `~/.dstack/server/config.yml` file:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
    backends:
    - type: kubernetes
      kubeconfig:
        filename: ~/.kube/config
      proxy_jump:
        hostname: 204.12.171.137
        port: 32000
```

</div>

### Proxy jump

To allow the `dstack` server and CLI to access runs via SSH, `dstack` requires a node that acts as a jump host to proxy SSH traffic into containers.  

To configure this node, specify `hostname` and `port` under the `proxy_jump` property:  

- `hostname` — the IP address of any cluster node selected as the jump host. Both the `dstack` server and CLI must be able to reach it. This node can be either a GPU node or a CPU-only node — it makes no difference.  
- `port` — any accessible port on that node, which `dstack` uses to forward SSH traffic.  

No additional setup is required — `dstack` configures and manages the proxy automatically.

### NVIDIA GPU Operator

> For `dstack` to correctly detect GPUs in your Kubernetes cluster, the cluster must have the
[NVIDIA GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/index.html) pre-installed.

After the backend is set up, you interact with `dstack` just as you would with other backends or SSH fleets. You can run dev environments, tasks, and services.

## Fleets

### Clusters

If you’d like to run [distributed tasks](../concepts/tasks.md#distributed-tasks) with the `kubernetes` backend, you first need to create a fleet with `placement` set to `cluster`:

<div editor-title="examples/misc/fleets/.dstack.yml">
    
    ```yaml
    type: fleet
    # The name is optional; if not specified, one is generated automatically
    name: my-k8s-fleet
    
    # For `kubernetes`, `min` should be set to `0` since it can't pre-provision VMs.
    # Optionally, you can set the maximum number of nodes to limit scaling.
    nodes: 0..

    placement: cluster
    
    backends: [kubernetes]
    
    resources:
      # Specify requirements to filter nodes
      gpu: 1..8
    ```
    
</div>

Then, create the fleet using the `dstack apply` command:

<div class="termy">

```shell
$ dstack apply -f examples/misc/fleets/.dstack.yml

Provisioning...
---> 100%

 FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
```

</div>

Once the fleet is created, you can run [distributed tasks](../concepts/tasks.md#distributed-tasks). `dstack` takes care of orchestration automatically.

For more details on clusters, see the [corresponding guide](clusters.md).

> Fleets with `placement` set to `cluster` can be used not only for distributed tasks, but also for dev environments, single-node tasks, and services.
> Since Kubernetes clusters are interconnected by default, you can always set `placement` to `cluster`.

!!! info "Fleets"
    It’s generally recommended to create [fleets](../concepts/fleets.md) even if you don’t plan to run distributed tasks.  

## FAQ

??? info "Is managed Kubernetes with auto-scaling supported?"
    Managed Kubernetes is supported. However, the `kubernetes` backend can only run on pre-provisioned nodes.  
    Support for auto-scalable Kubernetes clusters is coming soon—you can track progress in the corresponding [issue](https://github.com/dstackai/dstack/issues/3126).

    If on-demand provisioning is important, we recommend using [VM-based](../concepts/backends.md#vm-based) backends as they already support auto-scaling.
    
??? info "When should I use the Kubernetes backend?"
    Choose the `kubernetes` backend if your GPUs already run on Kubernetes and your team depends on its ecosystem and tooling. 

    If your priority is orchestrating cloud GPUs and Kubernetes isn’t a must, [VM-based](../concepts/backends.md#vm-based) backends are a better fit thanks to their native cloud integration.

    For on-prem GPUs where Kubernetes is optional, [SSH fleets](../concepts/fleets.md#ssh-fleets) provide a simpler and more lightweight alternative.
