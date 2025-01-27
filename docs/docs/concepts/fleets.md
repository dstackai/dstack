# Fleets

Fleets are groups of instances used to run dev environments, tasks, and services.
Depending on the fleet configuration, instances can be interconnected clusters or standalone instances.

`dstack` supports two kinds of fleets: 

* [Cloud fleets](#cloud) – dynamically provisioned through configured backends
* [SSH fleets](#ssh) – created using on-prem servers

## Cloud fleets { #cloud }

When you call `dstack apply` to run a dev environment, task, or service, `dstack` reuses `idle` instances 
from an existing fleet. If none match the requirements, `dstack` creates a new cloud fleet.

For greater control over cloud fleet provisioning, create fleets explicitly using configuration files. 

### Define a configuration

Define a fleet configuration as a YAML file in your project directory. The file must have a
`.dstack.yml` extension (e.g. `.dstack.yml` or `fleet.dstack.yml`).

<div editor-title="examples/misc/fleets/.dstack.yml">
    
    ```yaml
    type: fleet
    # The name is optional, if not specified, generated randomly
    name: my-fleet
    
    # Specify the number of instances
    nodes: 2
    # Uncomment to ensure instances are inter-connected
    #placement: cluster
    
    resources:
      gpu: 24GB
    ```
    
</div>

#### Placement { #cloud-placement }

To ensure instances are interconnected (e.g., for
[distributed tasks](tasks.md#distributed-tasks)), set `placement` to `cluster`. 
This ensures all instances are provisioned in the same backend and region with optimal inter-node connectivity

??? info "AWS"
    `dstack` automatically enables the Elastic Fabric Adapter for all
    [EFA-capable instance types :material-arrow-top-right-thin:{ .external }](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/efa.html#efa-instance-types){:target="_blank"}.
    Currently, only one EFA interface is enabled per instance, regardless of its maximum capacity.
    This will change once [this issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1804){:target="_blank"} is resolved.

> The `cluster` placement is supported only for `aws`, `azure`, `gcp`, `oci`, and `vultr`
> backends.

#### Resources

When you specify a resource value like `cpu` or `memory`,
you can either use an exact value (e.g. `24GB`) or a 
range (e.g. `24GB..`, or `24GB..80GB`, or `..80GB`).

<div editor-title=".dstack.yml"> 

```yaml
type: fleet
# The name is optional, if not specified, generated randomly
name: my-fleet

nodes: 2

resources:
  # 200GB or more RAM
  memory: 200GB..
  # 4 GPUs from 40GB to 80GB
  gpu: 40GB..80GB:4
  # Disk size
  disk: 500GB
```

</div>

The `gpu` property allows specifying not only memory size but also GPU vendor, names
and their quantity. Examples: `nvidia` (one NVIDIA GPU), `A100` (one A100), `A10G,A100` (either A10G or A100),
`A100:80GB` (one A100 of 80GB), `A100:2` (two A100), `24GB..40GB:2` (two GPUs between 24GB and 40GB),
`A100:40GB:2` (two A100 GPUs of 40GB).

??? info "Google Cloud TPU"
    To use TPUs, specify its architecture via the `gpu` property.

    ```yaml
    type: fleet
    # The name is optional, if not specified, generated randomly
    name: my-fleet
    
    nodes: 2

    resources:
      gpu: v2-8
    ```

    Currently, only 8 TPU cores can be specified, supporting single TPU device workloads. Multi-TPU support is coming soon.

#### Idle duration

By default, fleet instances stay `idle` for 3 days and can be reused within that time.
If the fleet is not reused within this period, it is automatically terminated.

To change the default idle duration, set
[`idle_duration`](../reference/dstack.yml/fleet.md#idle_duration) in the run configuration (e.g., `0s`, `1m`, or `off` for
unlimited).

<div editor-title="examples/misc/fleets/.dstack.yml">
    
    ```yaml
    type: fleet
    # The name is optional, if not specified, generated randomly
    name: my-fleet
    
    nodes: 2

    # Terminate instances idle for more than 1 hour
    idle_duration: 1h
    
    resources:
      gpu: 24GB
    ```
    
</div>

#### Spot policy

By default, `dstack` uses on-demand instances. However, you can change that
via the [`spot_policy`](../reference/dstack.yml/fleet.md#spot_policy) property. It accepts `spot`, `on-demand`, and `auto`.

#### Retry policy

By default, if `dstack` fails to provision an instance or an instance is interrupted, no retry is attempted.

If you'd like `dstack` to do it, configure the 
[retry](../reference/dstack.yml/fleet.md#retry) property accordingly:

<div editor-title=".dstack.yml">

```yaml
type: fleet
# The name is optional, if not specified, generated randomly
name: my-fleet

nodes: 1

resources:
  gpu: 24GB

retry:
  # Retry on specific events
  on_events: [no-capacity, interruption]
  # Retry for up to 1 hour
  duration: 1h
```

</div>

> Cloud fleets are supported by all backends except `kubernetes`, `vastai`, and `runpod`.

!!! info "Reference"
    Cloud fleets support many more configuration options,
    incl. [`backends`](../reference/dstack.yml/fleet.md#backends), 
    [`regions`](../reference/dstack.yml/fleet.md#regions), 
    [`max_price`](../reference/dstack.yml/fleet.md#max_price), and
    among [others](../reference/dstack.yml/fleet.md).

### Create or update a fleet

To create or update the fleet, pass the fleet configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f examples/misc/fleets/.dstack.yml
```

</div>

To ensure the fleet is created, you can use the `dstack fleet` command:

<div class="termy">

```shell
$ dstack fleet

 FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
 my-fleet  0         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago      
           1         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago    
```

</div>

Once the status of instances changes to `idle`, they can be used by dev environments, tasks, and services.

## SSH fleets { #ssh }

If you have a group of on-prem servers accessible via SSH, you can create an SSH fleet.

### Define a configuration

Define a fleet configuration as a YAML file in your project directory. The file must have a
`.dstack.yml` extension (e.g. `.dstack.yml` or `fleet.dstack.yml`).

<div editor-title="examples/misc/fleets/.dstack.yml"> 
    
    ```yaml
    type: fleet
    # The name is optional, if not specified, generated randomly
    name: my-fleet

    # Uncomment if instances are interconnected
    #placement: cluster

    # SSH credentials for the on-prem servers
    ssh_config:
      user: ubuntu
      identity_file: ~/.ssh/id_rsa
      hosts:
        - 3.255.177.51
        - 3.255.177.52
    ```
    
</div>

??? info "Requirements" 
    1.&nbsp;Hosts should be pre-installed with Docker.

    === "NVIDIA"
        2.&nbsp;Hosts with NVIDIA GPUs should also be pre-installed with CUDA 12.1 and
        [NVIDIA Container Toolkit :material-arrow-top-right-thin:{ .external }](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

    === "AMD"
        2.&nbsp;Hosts with AMD GPUs should also be pre-installed with AMDGPU-DKMS kernel driver (e.g. via
        [native package manager :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/native-install/index.html)
        or [AMDGPU installer :material-arrow-top-right-thin:{ .external }](https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/amdgpu-install.html).)

    3.&nbsp;The user specified should have passwordless `sudo` access.

#### Placement { #ssh-placement }

If the hosts are interconnected (i.e. share the same network), set `placement` to `cluster`. 
This is required if you'd like to use the fleet for [distributed tasks](tasks.md#distributed-tasks).

##### Network
    
By default, `dstack` automatically detects the network shared by the hosts. 
However, it's possible to configure it explicitly via 
the [`network`](../reference/dstack.yml/fleet.md#network) property.

[//]: # (TODO: Provide an example and more detail)

#### Environment variables

If needed, you can specify environment variables that will be used by `dstack-shim` and passed to containers.

[//]: # (TODO: Explain what dstack-shim is)

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
    For all SSH fleet configuration options, refer to the [reference](../reference/dstack.yml/fleet.md).

### Create or update a fleet

To create or update the fleet, pass the fleet configuration to [`dstack apply`](../reference/cli/dstack/apply.md):

<div class="termy">

```shell
$ dstack apply -f examples/misc/fleets/.dstack.yml
```

</div>

To ensure the fleet is created, you can use the `dstack fleet` command:

<div class="termy">

```shell
$ dstack fleet

 FLEET     INSTANCE  GPU             PRICE  STATUS  CREATED 
 my-fleet  0         L4:24GB (spot)  $0     idle    3 mins ago      
           1         L4:24GB (spot)  $0     idle    3 mins ago    
```

</div>

When you apply this configuration, `dstack` will connect to the specified hosts using the provided SSH credentials, 
install the dependencies, and configure these servers as a fleet.

Once the status of instances changes to `idle`, they can be used by dev environments, tasks, and services.

#### Troubleshooting

!!! info "Resources"
    Once the fleet is created, double-check that the GPU, memory, and disk are detected correctly.

If the status does not change to `idle` after a few minutes or the resources are not displayed correctly, ensure that
all host requirements are satisfied.

If the requirements are met but the fleet still fails to be created correctly, check the logs at
`/root/.dstack/shim.log` on the hosts for error details.

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
    1. Read about [dev environments](dev-environments.md), [tasks](tasks.md), and
    [services](services.md)
