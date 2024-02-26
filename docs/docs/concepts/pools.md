# Pools

Pools enable efficient lifecycle management of cloud instances and their reuse across runs.

- When an instance is provisioned in a configured backend, it is added to a pool.
- The instance is marked as busy while it runs the workload.
- Once the workload is finished, the instance is marked as ready (to run other workloads).
- If the instance remains idle for the configured duration, `dstack` tears it down.

## `dstack run`

By default, when you use the `dstack run` command, it attempts to reuse an instance from a pool. If there is no ready
instance that meets the requirements, `dstack` automatically provisions a new instance.

To solely use existing instances, pass the `--reuse` argument. In this scenario, the run will be assigned to an instance
once it's ready.

!!! info "Idle duration"
    By default, if `dstack run` provisions a new instance, its idle duration is set to `5m`. This means the instance waits for a
    new workload for only five minutes before getting torn down.
    To override it, use the `--idle-duration DURATION` argument.

## `dstack pool`

The `dstack pool` command allows for managing instances within pools as well as managing the pools themselves.

#### List instances 

The [`dstack pool ps`](../reference/cli/index.md#dstack-pool-ps) command lists all active instances and their status.

#### Add instances 

To manually add an instance to a pool, use [`dstack pool add`](../reference/cli/index.md#dstack-pool-add):

<div class="termy">

```shell
$ dstack pool add --gpu 80GB --idle-duration 1d

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y
```

</div>

The `dstack pool add` command allows specifying resource requirements, along with the spot policy, idle duration, max
price, retry policy, and other policies.

[//]: # (TODO: Mention the retry policy)

Alternatively, you can specify these policies via [`.dstack/profiles.yml`](../reference/profiles.yml.md) instead of passing them as arguments.
For more details on policies and their defaults, refer to [`.dstack/profiles.yml`](../reference/profiles.yml.md).

??? info "Limitations"
    The `dstack pool add` command is not yet supported for Lambda, Azure, TensorDock, Kubernetes, and VastAI backends. Support
    for them is coming in version `0.16.1`.

#### Remove instances

To remove an instance from a pool, use the `dstack pool remove` command. 

<div class="termy">

```shell
$ dstack pool remove &lt;instance name&gt;
```

</div>

!!! info "Idle time"
    If the instance remains idle for the configured duration, `dstack` removes it and deletes all cloud resources.

[//]: # (#### Manage pools)

[//]: # (TBA)

