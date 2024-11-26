# Troubleshooting

## Reporting issues

When you encounter a problem and need help, it's essential to report it as
a [GitHub issue :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/new/choose){:target="_blank"}.

> When bringing up issues on Discord, please include the steps to reproduce.

### Steps to reproduce

Make sure to provide clear, detailed steps to reproduce the issue. 
Include server logs, CLI outputs, and configuration samples. Avoid using screenshots for logs or errors—use text instead. 

To get more detailed logs, make sure to set the `DSTACK_CLI_LOG_LEVEL` and `DSTACK_SERVER_LOG_LEVEL` 
environment variables to `debug` when running the CLI and the server, respectively.

> See these examples for well-reported issues: [this :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1640){:target="_blank"}
and [this :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1551){:target="_blank"}.

## Typical issues

### Provisioning fails 

In certain cases, running `dstack apply` may produce the following output:

```shell
wet-mangust-1 provisioning completed (failed)
All provisioning attempts failed. This is likely due to cloud providers not having enough capacity. Check CLI and server logs for more details.
```

#### Backend configuration

If runs consistently fail to provision due to insufficient capacity, it’s likely there is a backend configuration issue.
Ensure that your backends are configured correctly and check the server logs for any errors.

#### Service quotas

If some runs fail to provision, it may be due to an insufficient service quota. For cloud providers like AWS, GCP,
Azure, and OCI, you often need to request an increased [service quota](protips.md#service-quotas) before you can use
specific instances.

#### Resources

Another possible cause of the insufficient capacity error is that `dstack` cannot find an instance that meets the
requirements specified in `resources`.

??? info "GPU"
    The `gpu` property allows you to specify the GPU name, memory, and quantity. Examples include `A100` (one GPU), `A100:40GB` (
    one GPU with exact memory), `A100:4` (four GPUs), etc. If you specify a GPU name without a quantity, it defaults to `1`. 
    
    If you request one GPU but only instances with eight GPUs are available, `dstack` won’t be able to provide it. Use range
    syntax to specify a range, such as `A100:1..8` (one to eight GPUs) or `A100:1..` (one or more GPUs).

??? info "Disk"
    If you don't specify the `disk` property, `dstack` defaults it to `100GB`. 
    In case there is no such instance available, `dstack` won’t be able to provide it. 
    Use range syntax to specify a range, such as `50GB..100GB` (from fifty GBs to one hundred GBs) or `50GB..` 
    (fifty GBs or more).

### Run fails

There could be several reasons for a run failing after successful provisioning. 

!!! info "Termination reason"
    To find out why a run terminated, use `--verbose` (or `-v`) with `dstack ps`.
    This will show the run's status and any failure reasons.

??? info "Diagnostic logs"
    You can get more information on why a run fails with diagnostic logs.
    Pass `--diagnose` (or `-d`) to `dstack logs` and you'll see logs of the run executor.

#### Spot interruption

If a run fails after provisioning with the termination reason `INTERRUPTED_BY_NO_CAPACITY`, it is likely that the run
was using spot instances and was interrupted. To address this, you can either set the
[`spot_policy`](../reference/dstack.yml/task.md#spot_policy) to `on-demand` or specify the 
[`retry`](../reference/dstack.yml/task.md#retry) property.

[//]: # (#### Other)
[//]: # (TODO: Explain how to get the shim logs)

### Can't run a service

#### Gateway configuration

If all services fail to start with a specific gateway, make sure a
[correct DNS record](../concepts/gateways.md#update-dns-records)
pointing to the gateway's hostname is configured.

### Service endpoint doesn't work 

#### Authorization

If the service endpoint returns a 403 error, it is likely because the [`Authorization`](../services.md#access-the-endpoint) 
header with the correct `dstack` token was not provided.

[//]: # (#### Other)
[//]: # (TODO: Explain how to get the gateway logs)

### Cannot access a dev environment or a task's ports

When running a dev environment or task with configured ports, `dstack apply` 
automatically forwards remote ports to `localhost` via SSH for easy and secure access.
If you interrupt the command, the port forwarding will be disconnected. To reattach, use `dstack attach <run name`.

#### Windows

If you're using the CLI on Windows, make sure to run it through WSL by following [these instructions:material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues/1644#issuecomment-2321559265){:target="_blank"}. 
Native support will be available soon.

### An SSH fleet doesn't provision

If you set up an SSH fleet and it fails to provision after a long wait, first check the server logs. 
Also, review the  `/root/.dstack/shim.log` file on each host used to create the fleet.

## Community

If you have a question, please feel free to ask it in our [Discord server](https://discord.gg/u8SmfwPpMd).
