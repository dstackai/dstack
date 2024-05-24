# Pools

Pools enable the efficient reuse of cloud instances and on-premises servers across runs, simplifying their management.

## Adding instances

### Automatic provisioning

By default, when using the `dstack run` command, it tries to reuse an instance from a pool. If no idle instance meets the
requirements, `dstack` automatically provisions a new cloud instance and adds it to the pool.

??? info "Reuse policy"
    To avoid provisioning new cloud instances with `dstack run`, use `--reuse`. Your run will be assigned to an idle instance in
    the pool.

??? info "Idle duration"
    By default, `dstack run` sets the idle duration of a newly provisioned instance to `5m`.
    This means that if the run is finished and the instance remains idle for longer than five minutes, it is automatically
    removed from the pool. To override the default idle duration, use  `--idle-duration DURATION` with `dstack run`.

### Manual provisioning

To manually provision a cloud instance and add it to a pool, use [`dstack pool add`](../reference/cli/index.md#dstack-pool-add):

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

??? info "Idle duration"
    The default idle duration if you're using `dstack pool add` is `72h`. To override it, use the `--idle-duration DURATION` argument.

[//]: # (TODO: Mention the retry policy)

You can also specify the policies via [`.dstack/profiles.yml`](../reference/profiles.yml.md) instead of passing them as arguments.
For more details on policies and their defaults, refer to [`.dstack/profiles.yml`](../reference/profiles.yml.md).

??? info "Limitations"
    The `dstack pool add` command is not supported for Kubernetes, VastAI, and RunPod backends yet.

### Adding on-prem servers

Any on-prem server that can be accessed via SSH can be added to a pool and used to run workloads.

To add on-prem servers to the pool, use the `dstack pool add-ssh` command and pass the hostname of your server along with
the SSH key.

<div class="termy">

```shell
$ dstack pool add-ssh -i ~/.ssh/id_rsa ubuntu@54.73.155.119
```

</div>

The command accepts the same arguments as the standard `ssh` command.

!!! warning "Requirements"
    The on-prem server should be pre-installed with CUDA 12.1 and NVIDIA Docker.

Once the instance is provisioned, you'll see it in the pool and will be able to run workloads on it.

#### Network

If you want on-prem instances to run multi-node tasks, ensure these on-prem servers share the same private network.
Additionally, you need to pass the `--network` option to `dstack pool add-ssh`:

<div class="termy">

```shell
$ dstack pool add-ssh -i ~/.ssh/id_rsa ubuntu@54.73.155.119 \
    --network 10.0.0.0/24
```

</div>

The `--network` argument accepts the IP address range (CIDR) of the private network of the instance.

Once you've added multiple instances with the same network value, you can use them as a cluster to run
[multi-node tasks](../reference/dstack.yml/task.md#_nodes).

## Removing instances

If the instance remains idle for the configured idle duration, `dstack` removes it and deletes all cloud resources.

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

