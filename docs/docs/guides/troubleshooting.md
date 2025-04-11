# Troubleshooting

## Reporting issues

When you encounter a problem, please report it as
a [GitHub issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/new/choose){:target="_blank"}.

If you have a question or need help, feel free to ask it in our [Discord server](https://discord.gg/u8SmfwPpMd).

> When bringing up issues, always include the steps to reproduce.

### Steps to reproduce

Make sure to provide clear, detailed steps to reproduce the issue. 
Include server logs, CLI outputs, and configuration samples. Avoid using screenshots for logs or errors—use text instead. 

To get more detailed logs, make sure to set the `DSTACK_CLI_LOG_LEVEL` and `DSTACK_SERVER_LOG_LEVEL` 
environment variables to `debug` when running the CLI and the server, respectively.

> See these examples for well-reported issues: [this :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1640){:target="_blank"}
and [this :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1551){:target="_blank"}.

## Typical issues

### No instance offers { #no-offers }
[//]: # (NOTE: This section is referenced in the CLI. Do not change its URL.)

If you run `dstack apply` and don't see any instance offers, it means that
`dstack` could not find instances that match the requirements in your configuration.
Below are some of the reasons why this might happen.

#### Cause 1: No capacity providers

Before you can run any workloads, you need to configure a [backend](../concepts/backends.md),
create an [SSH fleet](../concepts/fleets.md#ssh), or sign up for
[dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"}.
If you have configured a backend and still can't use it, check the output of `dstack server`
for backend configuration errors.

> **Tip**: You can find a list of successfully configured backends
> on the [project settings page](../concepts/projects.md#backends) in the UI.

#### Cause 2: Requirements mismatch

When you apply a configuration, `dstack` tries to find instances that match the
[`resources`](../reference/dstack.yml/task.md#resources),
[`backends`](../reference/dstack.yml/task.md#backends),
[`regions`](../reference/dstack.yml/task.md#regions),
[`availability_zones`](../reference/dstack.yml/task.md#availability_zones),
[`instance_types`](../reference/dstack.yml/task.md#instance_types),
[`spot_policy`](../reference/dstack.yml/task.md#spot_policy),
and [`max_price`](../reference/dstack.yml/task.md#max_price)
properties from the configuration.

`dstack` will only select instances that meet all the requirements.
Make sure your configuration doesn't set any conflicting requirements, such as
`regions` that don't exist in the specified `backends`, or `instance_types` that
don't match the specified `resources`.

#### Cause 3: Too specific resources

If you set a resource requirement to an exact value, `dstack` will only select instances
that have exactly that amount of resources. For example, `cpu: 5` and `memory: 10GB` will only
match instances that have exactly 5 CPUs and exactly 10GB of memory.

Typically, you will want to set resource ranges to match more instances.
For example, `cpu: 4..8` and `memory: 10GB..` will match instances with 4 to 8 CPUs
and at least 10GB of memory.

#### Cause 4: Default resources

By default, `dstack` uses these resource requirements:
`cpu: 2..`, `memory: 8GB..`, `disk: 100GB..`.
If you want to use smaller instances, override the `cpu`, `memory`, or `disk`
properties in your configuration.

#### Cause 5: GPU requirements

By default, `dstack` only selects instances with no GPUs or a single NVIDIA GPU.
If you want to use non-NVIDIA GPUs or multi-GPU instances, set the `gpu` property
in your configuration.

Examples: `gpu: amd` (one AMD GPU), `gpu: A10:4..8` (4 to 8 A10 GPUs),
`gpu: 8:Gaudi2` (8 Gaudi2 accelerators).

> If you don't specify the number of GPUs, `dstack` will only select single-GPU instances.

#### Cause 6: Network volumes

If your run configuration uses [network volumes](../concepts/volumes.md#network-volumes),
`dstack` will only select instances from the same backend and region as the volumes.
For AWS, the availability zone of the volume and the instance should also match.

#### Cause 7: Feature support

Some `dstack` features are not supported by all backends. If your configuration uses
one of these features, `dstack` will only select offers from the backends that support it.

- [Cloud fleet](../concepts/fleets.md#cloud) configurations,
  [Instance volumes](../concepts/volumes.md#instance-volumes),
  and [Privileged containers](../reference/dstack.yml/dev-environment.md#privileged)
  are supported by all backends except `runpod`, `vastai`, and `kubernetes`.
- [Clusters](../concepts/fleets.md#cloud-placement)
  and [distributed tasks](../concepts/tasks.md#distributed-tasks)
  are only supported by the `aws`, `azure`, `gcp`, `oci`, and `vultr` backends,
  as well as SSH fleets.
- [Reservations](../reference/dstack.yml/fleet.md#reservation)
  are only supported by the `aws` backend.

#### Cause 8: dstack Sky balance

If you are using
[dstack Sky :material-arrow-top-right-thin:{ .external }](https://sky.dstack.ai){:target="_blank"},
you will not see marketplace offers until you top up your balance.
Alternatively, you can configure your own cloud accounts
on the [project settings page](../concepts/projects.md#backends)
or use [SSH fleets](../concepts/fleets.md#ssh).

### Provisioning fails

In certain cases, running `dstack apply` may show instance offers,
but then produce the following output:

```shell
wet-mangust-1 provisioning completed (failed)
All provisioning attempts failed. This is likely due to cloud providers not having enough capacity. Check CLI and server logs for more details.
```

#### Cause 1: Insufficient service quotas

If some runs fail to provision, it may be due to an insufficient service quota. For cloud providers like AWS, GCP,
Azure, and OCI, you often need to request an increased [service quota](protips.md#service-quotas) before you can use
specific instances.

### Run starts but fails

There could be several reasons for a run failing after successful provisioning. 

!!! info "Termination reason"
    To find out why a run terminated, use `--verbose` (or `-v`) with `dstack ps`.
    This will show the run's status and any failure reasons.

!!! info "Diagnostic logs"
    You can get more information on why a run fails with diagnostic logs.
    Pass `--diagnose` (or `-d`) to `dstack logs` and you'll see logs of the run executor.

#### Cause 1: Spot interruption

If a run fails after provisioning with the termination reason `INTERRUPTED_BY_NO_CAPACITY`, it is likely that the run
was using spot instances and was interrupted. To address this, you can either set the
[`spot_policy`](../reference/dstack.yml/task.md#spot_policy) to `on-demand` or specify the 
[`retry`](../reference/dstack.yml/task.md#retry) property.

[//]: # (#### Other)
[//]: # (TODO: Explain how to get the shim logs)

### Services fail to start

#### Cause 1: Gateway misconfiguration

If all services fail to start with a specific gateway, make sure a
[correct DNS record](../concepts/gateways.md#update-dns-records)
pointing to the gateway's hostname is configured.

### Service endpoint doesn't work 

#### Cause 1: Bad Authorization

If the service endpoint returns a 403 error, it is likely because the [`Authorization`](../concepts/services.md#access-the-endpoint) 
header with the correct `dstack` token was not provided.

[//]: # (#### Other)
[//]: # (TODO: Explain how to get the gateway logs)

### Cannot access dev environment or task ports

#### Cause 1: Detached from run

When running a dev environment or task with configured ports, `dstack apply` 
automatically forwards remote ports to `localhost` via SSH for easy and secure access.
If you interrupt the command, the port forwarding will be disconnected. To reattach, use `dstack attach <run name`.

#### Cause 2: Windows

If you're using the CLI on Windows, make sure to run it through WSL by following [these instructions:material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1644#issuecomment-2321559265){:target="_blank"}. 
Native support will be available soon.

### SSH fleet fails to provision

If you set up an SSH fleet and it fails to provision after a long wait, first check the server logs. 
Also, review the  `/root/.dstack/shim.log` file on each host used to create the fleet.

## Community

If you have a question, please feel free to ask it in our [Discord server](https://discord.gg/u8SmfwPpMd).
