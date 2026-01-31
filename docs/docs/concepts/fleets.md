---
title: Fleets
description: Managing pools of compute instances
---

# Fleets

Before submitting runs, you must create a fleet. Fleets act as both pools of instances and templates for how those instances are provisioned.

> `dstack` supports two fleet types: [backend fleets](#backend-fleet) (which are provisioned dynamically in the cloud or on Kubernetes), and [SSH fleets](#ssh-fleet) (which use existing on-prem servers).

## Apply a configuration

To create a fleet, define its configuration in a YAML file. The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `fleet.dstack.yml`), regardless of fleet type.

=== "Backend fleets"
    If you're using cloud providers or Kubernetes clusters and have configured the corresponding [backends](backends.md), create a backend fleet as follows:

    <div editor-title="fleet.dstack.yml"> 

    ```yaml
    type: fleet
    name: my-fleet

    # Allow to provision of up to 2 instances
    nodes: 0..2

    # Uncomment to ensure instances are inter-connected
    #placement: cluster

    # Deprovision instances above the minimum if they remain idle
    idle_duration: 1h

    resources:
      # Allow to provision up to 8 GPUs
      gpu: 0..8
    ```

    </div>

    Pass the fleet configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f fleet.dstack.yml
        
      #  BACKEND  REGION           RESOURCES                 SPOT  PRICE
      1  gcp      us-west4         2xCPU, 8GB, 100GB (disk)  yes   $0.010052
      2  azure    westeurope       2xCPU, 8GB, 100GB (disk)  yes   $0.0132
      3  gcp      europe-central2  2xCPU, 8GB, 100GB (disk)  yes   $0.013248

    Create the fleet? [y/n]: y

      FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
      my-fleet  0         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago      
                1         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago    
    ```

    </div>

    If the `nodes` range starts with `0`, `dstack apply` creates only a template. Instances are provisioned only when you submit runs.

=== "SSH fleets"
    If you have a group of on-prem servers accessible via SSH, you can create an SSH fleet as follows:

    <div editor-title="fleet.dstack.yml"> 
    
    ```yaml
    type: fleet
    name: my-fleet
    
    # Uncomment if instances are interconnected
    #placement: cluster

    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/id_rsa
      hosts:
        - 3.255.177.51
        - 3.255.177.52
    ```
      
    </div>

    Pass the fleet configuration to `dstack apply`:

    <div class="termy">

    ```shell
    $ dstack apply -f fleet.dstack.yml
        
    Provisioning...
    ---> 100%

      FLEET     INSTANCE  BACKEND       GPU      PRICE  STATUS  CREATED 
      my-fleet  0         ssh (remote)  L4:24GB  $0     idle    3 mins ago      
                1         ssh (remote)  L4:24GB  $0     idle    3 mins ago    
    ```

    </div>

    `dstack apply` automatically connects to on-prem servers, installs the required dependencies, and adds them to the created fleet.

    ??? info "Host requirements"
        1.&nbsp;Hosts must be pre-installed with Docker.

        === "NVIDIA"
            2.&nbsp;Hosts with NVIDIA GPUs must also be pre-installed with CUDA 12.1 and
            [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

        === "AMD"
            2.&nbsp;Hosts with AMD GPUs must also be pre-installed with AMDGPU-DKMS kernel driver (e.g. via
            [native package manager](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/native-install/index.html)
            or [AMDGPU installer](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/amdgpu-install.html).)

        === "Intel Gaudi"
            2.&nbsp;Hosts with Intel Gaudi accelerators must be pre-installed with [Gaudi software and drivers](https://docs.habana.ai/en/latest/Installation_Guide/Driver_Installation.html#driver-installation).
            This must include the drivers, `hl-smi`, and Habana Container Runtime.

        === "Tenstorrent"
            2.&nbsp;Hosts with Tenstorrent accelerators must be pre-installed with [Tenstorrent software](https://docs.tenstorrent.com/getting-started/README.html#software-installation).
            This must include the drivers, `tt-smi`, and HugePages.

        3.&nbsp;The user specified must have passwordless `sudo` access.

        4.&nbsp;The SSH server must be running and configured with `AllowTcpForwarding yes` in `/etc/ssh/sshd_config`.

        5.&nbsp;The firewall must allow SSH and should forbid any other connections from external networks. For `placement: cluster` fleets, it should also allow any communication between fleet nodes.

> Once the fleet is created, you can run [dev environments](dev-environments.md), [tasks](tasks.md), and [services](services.md).

## Configuration options

Backend fleets support [many options](../reference/dstack.yml/fleet.md); see some major configuration examples below.

### Cluster placement

Both [backend fleets](#backend-fleet) and [SSH fleets](#ssh-fleet) allow the `placement` property to be set to `cluster`. 

This property ensures that instances are interconnected. This is required for running [distributed tasks](tasks.md#distributed-tasks).

=== "Backend fleets"
    Backend fleets allow to provision interconnected clusters across supported backends.

    <div editor-title="fleet.dstack.yml">
        
    ```yaml
    type: fleet
    name: my-fleet
    
    nodes: 2
    placement: cluster
    
    resources:
      gpu: H100:8
    ```
        
    </div>

    #### Backends

    Fast interconnect is supported on the `aws`, `gcp`, `nebius`, `kubernetes`, and `runpod` backends. Some backends may require additional configuration.

    === "AWS"
        On AWS, `dstack` requires `public_ips` to be set to `false` in the backend configuration.
        Refer to the [AWS](../../examples/clusters/aws/index.md) example for more details.

    === "GCP"
        On GCP, you may need to configure `extra_vpcs` and `roce_vpcs` in the `gcp` backend configuration.
        Refer to the [GCP](../../examples/clusters/gcp/index.md) examples for more details.

    === "Nebius"
        On [Nebius](https://docs.nebius.com/compute/clusters/gpu), `dstack` automatically configures InfiniBand networking if it is supported by the selected instance type.

    === "Kubernetes"
        If the Kubernetes cluster has interconnect configured, `dstack` can use it without additional setup.
        See the [Lambda](../../examples/clusters/lambda/index.md#kubernetes) or [Crusoe](../../examples/clusters/crusoe/index.md#kubernetes) examples.
    
    === "Runpod"
        On [Runpod](https://docs.runpod.io/instant-clusters), `dstack` automatically configures InfiniBand networking if it is supported by the selected instance type.
    
    > See the [Clusters](../../examples.md#clusters) examples.

=== "SSH fleets"
    If the hosts in the SSH fleet have interconnect configured, you only need to set `placement` to `cluster`.

    <div editor-title="fleet.dstack.yml"> 
        
    ```yaml
    type: fleet
    name: my-fleet

    placement: cluster

    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/id_rsa
      hosts:
        - 3.255.177.51
        - 3.255.177.52
    ```
      
    </div>

    !!! info "Network"
        By default, `dstack` automatically detects the network shared by the hosts. However, it's possible to configure it explicitly via the [`network`](../reference/dstack.yml/fleet.md#network) property.

        <!-- TODO: Add network configuration example -->

### Nodes

The `nodes` property is supported only by backend fleets and specifies how many nodes `dstack` must or can provision.

<div editor-title="fleet.dstack.yml"> 

```yaml
type: fleet
name: my-fleet

# Allow to provision of up to 2 instances
nodes: 0..2

# Uncomment to ensure instances are inter-connected
#placement: cluster

# Deprovision instances above the minimum if they remain idle
idle_duration: 1h

resources:
  # Allow to provision up to 8 GPUs
  gpu: 0..8
```

</div>

#### Pre-provisioning

If the `nodes` range starts with `0`, `dstack apply` creates only a template, and instances are provisioned when you submit runs.

To provision instances up front, set the `nodes` range to start above `0`. This pre-creates the initial number of instances; additional instances (if any) are provisioned on demand.


<div editor-title="fleet.dstack.yml">
        
    ```yaml
    type: fleet
    name: my-fleet
    
    nodes: 2..10

    # Uncomment to ensure instances are inter-connected
    #placement: cluster
    
    resources:
      gpu: H100:8
    ```
        
    </div>

Pre-provisioning is supported only for [VM-based backends](backends.md#vm-based).

??? info "Target number"
    To pre-provision more than the minimum number of instances, set the `target` parameter.

    <div editor-title="fleet.dstack.yml"> 

    ```yaml
    type: fleet
    name: my-fleet

    nodes:
      min: 2
      max: 10
      target: 6

    # Deprovision instances above the minimum if they remain idle
    idle_duration: 1h
    ```

    </div>

    `dstack apply` pre-provisions up to `target` and scales back to `min` after `idle_duration`.

### Resources

Backend fleets allow you to specify the resource requirements for the instances to be provisioned. The `resources` property syntax is the same as for [run configurations](dev-environments.md#resources).

### Spot policy

Backend fleets allow you to specify a `spot policy`. By default, it is set to `on-demand`. If you want to use spot instances, you must set it to `auto` if you plan to use both on-demand and spot instances, or to `spot` if only spot instances are allowed.

<div editor-title="fleet.dstack.yml"> 

```yaml
type: fleet
name: my-fleet

nodes: 0..2

# Uncomment to ensure instances are inter-connected
#placement: cluster

# Allows both on-demand and spot
spot_policy: auto

idle_duration: 1h

resources:
  gpu: 0..8
```

</div>

Note that run configurations must specify their own `spot policy` which is also set to `on-demand` by default.

### Backends

Backend fleets allow you to set `backends` to specify which backends are allowed to be used.

### Idle duration

By default, instances of a backend fleet stay `idle` for 3 days and can be reused within that time.
If an instance is not reused within this period, it is automatically terminated.

To change the default idle duration, set
[`idle_duration`](../reference/dstack.yml/fleet.md#idle_duration) in the fleet configuration (e.g., `0s`, `1m`, or `off` for
unlimited).

<div editor-title="fleet.dstack.yml">
    
```yaml
type: fleet
name: my-fleet

nodes: 2

# Terminate instances idle for more than 1 hour
idle_duration: 1h

resources:
  gpu: 24GB
```

</div>

### Blocks

By default, a job uses the entire instance—e.g., all 8 GPUs. To allow multiple jobs on the same instance, set the `blocks` property to divide the instance. Each job can then use one or more blocks, up to the full instance.

=== "Backend fleets"
    <div editor-title=".dstack.yml">

    ```yaml
    type: fleet
    name: my-fleet

    nodes: 0..2

    resources:
      gpu: H100:8

    # Split into 4 blocks, each with 2 GPUs
    blocks: 4
    ```

    </div>

=== "SSH fleets"
    <div editor-title=".dstack.yml">

    ```yaml
    type: fleet
    name: my-fleet

    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/id_rsa
      hosts:
        - hostname: 3.255.177.51
          blocks: 4
        - hostname: 3.255.177.52
          # As many as possible, according to numbers of GPUs and CPUs
          blocks: auto
        - hostname: 3.255.177.53
          # Do not slice. This is the default value, may be omitted
          blocks: 1
    ```

    </div>

All resources (GPU, CPU, memory) are split evenly across blocks, while disk is shared.

For example, with 8 GPUs, 128 CPUs, and 2TB RAM, setting `blocks` to `8` gives each block 1 GPU, 16 CPUs, and 256 GB RAM.

Set `blocks` to `auto` to match the number of blocks to the number of GPUs.

!!! info "Distributed tasks"
    Distributed tasks require exclusive access to all host resources and therefore must use all blocks on each node.

### SSH config

<!-- TODO: add more detail -->

#### Proxy jump

If hosts are behind a head node (aka "login node"), configure [`proxy_jump`](../reference/dstack.yml/fleet.md#proxy_jump):

<div editor-title="fleet.dstack.yml">

    ```yaml
    type: fleet
    name: my-fleet

    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/worker_node_key
      hosts:
        - 3.255.177.51
        - 3.255.177.52
      proxy_jump:
        hostname: 3.255.177.50
        user: ubuntu
        identity_file: ~/.ssh/head_node_key
    ```

</div>

To be able to attach to runs, both explicitly with `dstack attach` and implicitly with `dstack apply`, you must either add a front node key (`~/.ssh/head_node_key`) to an SSH agent or configure a key path in `~/.ssh/config`:

<div editor-title="~/.ssh/config">

    ```
    Host 3.255.177.50
        IdentityFile ~/.ssh/head_node_key
    ```

</div>

where `Host` must match `ssh_config.proxy_jump.hostname` or `ssh_config.hosts[n].proxy_jump.hostname` if you configure head nodes on a per-worker basis.

### Environment variables

If needed, you can specify environment variables that will be automatically passed to any jobs running on this fleet.

For example, these variables can be used to configure a proxy:

```yaml
type: fleet
name: my-fleet

env:
  - HTTP_PROXY=http://proxy.example.com:80
  - HTTPS_PROXY=http://proxy.example.com:80
  - NO_PROXY=localhost,127.0.0.1

ssh_config:
  user: ubuntu
  identity_file: ~/.ssh/id_rsa
  hosts:
    - 3.255.177.51
    - 3.255.177.52
```

!!! info "Reference"
    The fleet configuration file supports additional options, including [`instance_types`](../reference/dstack.yml/fleet.md#instance_types), [`max_price`](../reference/dstack.yml/fleet.md#max_price), [`regions`](../reference/dstack.yml/fleet.md#max_price), among others. For the complete list, see the [reference](../reference/dstack.yml/fleet.md).

## Manage fleets

### List fleets

The [`dstack fleet`](../reference/cli/dstack/fleet.md#dstack-fleet-list) command lists fleet instances and their status:

<div class="termy">

```shell
$ dstack fleet

 FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
 my-fleet  0         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago      
           1         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago    
```

</div>

### Delete fleets

When a fleet isn't used by a run, you can delete it by passing the fleet configuration to `dstack delete`:

<div class="termy">

```shell
$ dstack delete -f cluster.dstack.yaml
Delete the fleet my-gcp-fleet? [y/n]: y
Fleet my-gcp-fleet deleted
```

</div>

Alternatively, you can delete a fleet by passing the fleet name  to `dstack fleet delete`.
To terminate and delete specific instances from a fleet, pass `-i INSTANCE_NUM`.

!!! info "What's next?"
    1. Check [dev environments](dev-environments.md), [tasks](tasks.md), and
    [services](services.md)
    2. Read about [Backends](backends.md) guide
    3. Explore the [`.dstack.yml` reference](../reference/dstack.yml/fleet.md)
    4. See the [Clusters](../../examples.md#clusters) example
