# Fleets

Fleets are groups of cloud instances or SSH machines that you use to run dev environments, tasks, and services.

By default, when you run `dstack apply` to start a new dev environment, task, or service,
`dstack` reuses `idle` instances from an existing fleet.
If no `idle` instances match the requirements, `dstack` automatically creates a new fleet 
using configured backends.

If you need more control over instance configuration and lifecycle, or if you want to use on-prem servers,
`dstack` also offers you a way to create and manage fleets directly.

## Define a configuration

To create a fleet, define its configuration as a YAML file in your project folder.
The filename must end with `.dstack.yml` (e.g. `.dstack.yml` or `fleet.dstack.yml` are both acceptable).

=== "Cloud fleets"

    !!! info "What is a cloud fleet?"
        By default, when running dev environments, tasks, and services, `dstack` 
        reuses `idle` instances from existing fleets or creates a new cloud fleet on the fly.
        
        If you want more control over the lifecycle of cloud instances, you can create a cloud fleet manually. 
        This allows you to reuse a fleet over a longer period and across multiple runs. You can also delete the fleet only when needed.

    To create a cloud fleet, specify `resources`, `nodes`, 
    and other optional parameters.
    
    <div editor-title="examples/misc/fleets/distrib.dstack.yml">
    
    ```yaml
    type: fleet
    # The name is optional, if not specified, generated randomly
    name: fleet-distrib
    
    # Number of instances
    nodes: 2
    # Ensure instances are inter-connected
    placement: cluster
    
    # Terminate if idle for 3 days
    idle_duration: 3d 

    resources:
      gpu:
        # 24GB or more vRAM
        memory: 24GB..
        # Two or more GPUs
        count: 2..
    ```
    
    </div>
    
    When you apply this configuration, `dstack` will create cloud instances using the configured backends according 
    to the specified parameters.

    !!! info "Cluster placement"
        To ensure the nodes of the fleet are interconnected (e.g., if you'd like to use them for
        [multi-node tasks](../reference/dstack.yml/task.md#distributed-tasks)), 
        set `placement` to `cluster`. 
        
        In this case, `dstack` will provision all nodes in the same backend and region and configure optimal 
        inter-node connectivity.

        !!! info "Backends"
            The `cluster` value of the `placement` property is supported only by the `aws`, `azure`, `gcp`, and `oci`
            backends.

        ??? info "AWS"
            `dstack` automatically enables [Elastic Fabric Adapter :material-arrow-top-right-thin:{ .external }](https://aws.amazon.com/hpc/efa/){:target="_blank"}
            for instance types that support it. The following instance types with EFA are supported:
            `p5.48xlarge`, `p4d.24xlarge`, `g4dn.12xlarge`, `g4dn.16xlarge`, `g4dn.8xlarge`, `g4dn.metal`,
            `g5.12xlarge`, `g5.16xlarge`, `g5.24xlarge`, `g5.48xlarge`, `g5.8xlarge`, `g6.12xlarge`,
            `g6.16xlarge`, `g6.24xlarge`, `g6.48xlarge`, `g6.8xlarge`, `gr6.8xlarge`

            Currently, only one EFA interface is enabled regardless of the maximum number of interfaces supported by the instance type.
            This limitation will be lifted once [this issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1804){:target="_blank"} is fixed.

    !!! info "Backends"
        Cloud fleets are supported for all backends except `kubernetes`, `vastai`, and `runpod`.

=== "SSH fleets"

    !!! info "What is an SSH fleet?"
        If you’d like to run dev environments, tasks, and services on arbitrary on-prem servers via `dstack`, you can 
        create an SSH fleet.

    To create an SSH fleet, specify `ssh_config` to allow the `dstack` server to connect to these servers
    via SSH.

    <div editor-title="examples/misc/fleets/distrib-ssh.dstack.yml"> 
    
    ```yaml
    type: fleet
    # The name is optional, if not specified, generated randomly
    name: fleet-distrib-ssh

    # Ensure instances are inter-connected
    placement: cluster

    # The user, private SSH key, and hostnames of the on-prem servers
    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/id_rsa
      hosts:
        - 3.255.177.51
        - 3.255.177.52
    ```
    
    </div>

    When you apply this configuration, `dstack` will connect to the specified hosts using the provided SSH credentials, 
    install the dependencies, and configure these servers as a fleet.

    !!! info "Requirements" 
        Hosts should be pre-installed with Docker.

        === "NVIDIA"
            Systems with NVIDIA GPUs should also be pre-installed with CUDA 12.1 and
            [NVIDIA Container Toolkit :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

        === "AMD"
            Systems with AMD GPUs should also be pre-installed with AMDGPU-DKMS kernel driver (e.g. via
            [native package manager :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/native-install/index.html)
            or [AMDGPU installer :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/amdgpu-install.html).)

        The user should have passwordless `sudo` access.

    ??? info "Environment variables"
        For SSH fleets, it's possible to pre-configure environment variables. 
        These variables will be used when installing the `dstack-shim` service on hosts 
        and running containers.

        For example, these variables can be used to configure a proxy:

        ```yaml
        type: fleet
        name: my-fleet
        
        placement: cluster
        
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

    !!! info "Cluster placement"
        Set `placement` to `cluster` if the hosts are interconnected
        (e.g. if you'd like to use them for [multi-node tasks](../reference/dstack.yml/task.md#distributed-tasks)).
        
        !!! info "Network"
            By default, `dstack` automatically detects the private network for the specified hosts. 
            However, it's possible to configure it explicitelly via 
            the [`network`](../reference/dstack.yml/fleet.md#network) property.

    !!! info "Backends"
        To use SSH fleets, you don't need to configure any backends at all.

!!! info "Reference"
    See [`.dstack.yml`](../reference/dstack.yml/fleet.md) for all the options supported by
    the fleet configuration.

## Create or update a fleet

To create or update the fleet, pass the fleet configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f examples/misc/fleets/distrib.dstack.yml
```

</div>

### Ensure the fleet is created

To ensure the fleet is created, use the `dstack fleet` command:

<div class="termy">

```shell
$ dstack fleet

 FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
 my-fleet  0         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago      
           1         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago    
```

</div>

Once the status of instances changes to `idle`, they can be used by dev environments, tasks, and services.

!!! info "Idle duration"
    If you want a fleet to be automatically deleted after a certain idle time,
    you can set the [`idle_duration`](../reference/dstack.yml/fleet.md#idle_duration) property.
    By default, it's set to `3d`.

[//]: # (Add Idle time example to the reference page)

### Troubleshooting SSH fleets

!!! info "Resources"
    If you're creating an SSH fleet, ensure that the GPU, memory, and disk size are detected properly.
    If GPU isn't detected, ensure that the hosts meet the requirements (see above).

If the status doesn't change to `idle` after a few minutes, ensure that 
the hosts meet the requirements (see above).

If the requirements are met but the fleet still fails to be created, check `/root/.dstack/shim.log` for logs 
on the hosts specified in `ssh_config`.

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

## What's next?

1. Read about [dev environments](../dev-environments.md), [tasks](../tasks.md), and 
    [services](../services.md) 
2. Join the community via [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd)

!!! info "Reference"
    See [.dstack.yml](../reference/dstack.yml/fleet.md) for all the options supported by
    fleets, along with multiple examples.
