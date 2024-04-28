# Pools

Pools simplify managing the lifecycle of cloud instances and enable their efficient reuse across runs.

You can have instances provisioned in the configured backend automatically when you run a workload, or add them
manually, configuring the required resources, idle duration, etc.

## Add instances

### dstack run

By default, when using the `dstack run` command, it tries to reuse an instance from a pool. If no idle instance meets the
requirements, `dstack` automatically provisions a new one and adds it to the pool.

To avoid provisioning new instances with `dstack run`, use `--reuse`. Your run will be assigned to an idle instance in 
the pool.

!!! info "Idle duration"
    By default, `dstack run` sets the idle duration of a newly provisioned instance to `5m`.
    This means that if the run is finished and the instance remains idle for longer than five minutes, it is automatically
    removed from the pool. To override the default idle duration, use  `--idle-duration DURATION` with `dstack run`.

### dstack pool add 

To manually add an instance to a pool, use [`dstack pool add`](../reference/cli/index.md#dstack-pool-add):

<div class="termy">

```shell
$ dstack pool add --gpu 80GB

 BACKEND     REGION         RESOURCES                     SPOT  PRICE
 tensordock  unitedkingdom  10xCPU, 80GB, 1xA100 (80GB)   no    $1.595
 azure       westus3        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 azure       westus2        24xCPU, 220GB, 1xA100 (80GB)  no    $3.673
 
Continue? [y/n]: y
```

</div>

The `dstack pool add` command allows specifying resource requirements, along with the spot policy, idle duration, max
price, retry policy, and other policies.

The default idle duration if you're using `dstack pool add` is `72h`. To override it, use the `--idle-duration DURATION` argument.

[//]: # (TODO: Mention the retry policy)

You can also specify the policies via [`.dstack/profiles.yml`](../reference/profiles.yml.md) instead of passing them as arguments.
For more details on policies and their defaults, refer to [`.dstack/profiles.yml`](../reference/profiles.yml.md).

??? info "Limitations"
    The `dstack pool add` command is not supported for Kubernetes, and VastAI backends yet.

## Remove instances

!!! info "Idle duration"
    If the instance remains idle for the configured duration, `dstack` removes it and deletes all cloud resources.

### dstack pool remove

To remove an instance from the pool manually, use the `dstack pool remove` command. 

<div class="termy">

```shell
$ dstack pool remove &lt;instance name&gt;
```

</div>

## List instances 

The [`dstack pool ps`](../reference/cli/index.md#dstack-pool-ps) command lists active instances and their status (`busy`
or `idle`).

[//]: # (#### Manage pools)

[//]: # (TBA)

