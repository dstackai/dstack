# Fleets

Fleets enable efficient provisioning and management of clusters and instances, both in the cloud and on-prem. Once a
fleet is created, it can be reused by dev environments, tasks, and services.

> Fleets is a new feature. To use it, ensure you've installed version `0.18.7` or higher.

## Configuration

To create a fleet, create a YAML file in your project folder. Its name must end with `.dstack.yml` (e.g. `.dstack.yml` or `fleet.dstack.yml`
are both acceptable).

=== "Cloud fleets"

    To provision a fleet in the cloud using the configured backends, specify the required resources, number of nodes, 
    and other optional parameters.
    
    <div editor-title="examples/fleets/cluster.dstack.yml">
    
    ```yaml
    type: fleet
    name: my-fleet
    
    nodes: 2
    placement: cluster
    
    backends: [aws]
    
    resources:
      gpu: 24GB
    ```
    
    </div>

    Set `placement` to `cluster` if the nodes should be interconnected (e.g. if you'd like to use them for multi-node tasks). 
    In that case, `dstack` will provision all nodes in the same backend and region.
    
    Defining fleets with YAML isn't supported yet for the `kubernetes`, `vastai`, and `runpod` backends.

=== "On-prem fleets"

    To create a fleet from on-prem servers, specify their hosts along with the user, port, and SSH key for connection via SSH.

    <div editor-title="examples/fleets/cluster.dstack.yml"> 
    
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

    !!! warning "Requirements"
        The on-prem servers should be pre-installed with CUDA 12.1 and NVIDIA Docker. 
        The user should have `sudo` access.

    Set `placement` to `cluster` if the nodes are interconnected (e.g. if you'd like to use them for multi-node tasks).
    In that case, by default, `dstack` will automatically detect the private network. 
    You can specify the [`network`](../reference/dstack.yml/fleet.md#network) parameter manually.

!!! info "Reference"
    See the [.dstack.yml reference](reference/dstack.yml/fleet.md)
    for all supported configuration options and examples.

## Creating and updating fleets

To create or update the fleet, simply call the [`dstack apply`](reference/cli/index.md#dstack-apply) command:

<div class="termy">

```shell
$ dstack apply -f examples/fleets/cluster.dstack.yml
Fleet my-fleet does not exist yet. Create the fleet? [y/n]: y
 FLEET     INSTANCE  BACKEND  RESOURCES  PRICE  STATUS   CREATED 
 my-fleet  0                                    pending  now     
           1                                    pending  now     
```

</div>

Once the status of instances change to `idle`, they can be used by `dstack run`.

## Creation policy

> By default, `dstack run` tries to reuse `idle` instances from existing fleets. 
If no `idle` instances meet the requirements, `dstack run` creates a new fleet automatically.
To avoid creating new fleet, specify pass `--reuse` to `dstack run`.

## Termination policy

> If you want a fleet to be automatically deleted after a certain idle time, you can set the 
you can set the [`termination_idle_time`](reference/dstack.yml/fleet.md#termination_idle_time) property.

## Managing fleets

### Listing fleets

The [`dstack fleet`](reference/cli/index.md#dstack-gateway-list) command lists fleet instances and theri status:

<div class="termy">

```
$ dstack fleet
 FLEET     INSTANCE  BACKEND              GPU             PRICE    STATUS  CREATED 
 my-fleet  0         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago      
           1         gcp (europe-west-1)  L4:24GB (spot)  $0.1624  idle    3 mins ago    
```

</div>

### Deleting fleets

When a fleet isn't used by run, you can delete it via `dstack delete`:

<div class="termy">

```shell
$ dstack delete -f cluster.dstack.yaml
Delete the fleet my-gcp-fleet? [y/n]: y
Fleet my-gcp-fleet deleted
```

</div>

You can pass either the path to the configuration file or the fleet name directly.

To terminate and delete specific instances from a fleet, pass `-i INSTANCE_NUM`.