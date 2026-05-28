---
title: Tenant isolation
description: Restricting access to hosts managed by dstack
---

# Tenant isolation

`dstack` assumes mutual trust between users of the same project. While users' jobs run in Docker containers, users and their containers may have broad access to the underlying hosts. This guide explains how to restrict access to the host when stronger boundaries are required.

!!! info "Disclaimer"
    Even with all precautions, complete isolation on shared hardware is hardly achievable — container escape vulnerabilities are common. The best way to provide true isolation between users is to place them in different `dstack` projects and not share hardware between them.

## Host SSH access

While attached to a run, users can SSH directly into the host machine — not just the container — using:

```shell
ssh <run-name>-host
```

This gives unrestricted access to the underlying instance, bypassing container boundaries.

If desired, host SSH access can be disabled server-wide by configuring the [SSH proxy](server-deployment.md#ssh-proxy) and setting the following environment variable when starting the `dstack` server:

```shell
DSTACK_SERVER_SSHPROXY_ENFORCED=1
```

With this setting, all users' SSH connections go through the SSH proxy, which only allows connections into the container and not into the host.

## Privileged mode

Running a container in privileged mode gives it full access to the host kernel, making container escape straightforward. `dstack` supports requesting privileged mode through several configuration properties:

| Property | Applies to |
|---|---|
| `privileged: true` | Tasks, dev environments, services |
| `docker: true` | Tasks, dev environments, services |
| `replicas[i].privileged: true` | Services with replica groups |
| `replicas[i].docker: true` | Services with replica groups |

To block runs that request privileged mode, write a [REST plugin](../reference/plugins/rest/index.md) or a [Python plugin](../reference/plugins/python/index.md) with an apply policy.

<div editor-title="src/isolation_plugin/__init__.py">

```python
class NoPrivilegedPolicy(ApplyPolicy):
    def on_run_apply(self, user: str, project: str, spec: RunSpec) -> RunSpec:
        conf = spec.configuration

        if conf.privileged or conf.docker:
            raise ValueError("Privileged mode and Docker-in-Docker are not allowed")

        if isinstance(conf, ServiceConfiguration) and isinstance(conf.replicas, list):
            for group in conf.replicas:
                if group.privileged or group.docker:
                    raise ValueError(
                        f"Replica group '{group.name}' requests privileged mode, which is not allowed"
                    )

        return spec
```

</div>

## Instance volumes

[Instance volumes](../concepts/volumes.md#instance-volumes) mount a path from the host filesystem directly into the container. A user with access to this feature can mount arbitrary host paths — including sensitive directories such as `/etc`, `/proc`, or `/var`.

You can disallow instance volumes or restrict access to certain paths by writing a [REST plugin](../reference/plugins/rest/index.md) or a [Python plugin](../reference/plugins/python/index.md).

## Host network access

By default, most `dstack` jobs run in host networking mode. This allows them to listen on any host network interface and communicate with other jobs over the internal network, which facilitates workloads such as [distributed tasks](../concepts/tasks.md#distributed-tasks) or [services with routers](../concepts/services.md#pd-disaggregation).

However, exposing the host network to the job also exposes internal `dstack` APIs used to manage containers and SSH authorized keys on the host. If this is not acceptable, bridge networking should be used, which isolates the job from the host network. Bridge networking, however, breaks workloads that do need inter-job communication.

The `DSTACK_SERVER_JOB_NETWORK_MODE` environment variable controls which jobs get host vs. bridge networking:

| Value | Name | Behavior |
|---|---|---|
| `1` | `HOST_FOR_MULTINODE_ONLY` | Host for distributed tasks, bridge otherwise |
| `2` | `HOST_WHEN_POSSIBLE` | Host whenever the job occupies a full instance (default) |
| `3` | `FORCED_BRIDGE` | Always bridge, including distributed tasks |

### No distributed tasks

If you don't need distributed tasks or other runs with inter-job communication, you can set `DSTACK_SERVER_JOB_NETWORK_MODE=3` when starting the server:

```shell
DSTACK_SERVER_JOB_NETWORK_MODE=3
```

This forces bridge networking for all jobs on the server without exception, preventing access to internal `dstack` APIs, as well as communication between jobs.

### Allow distributed tasks in selected projects

If you want distributed tasks or other runs with inter-job communication to be available in some projects but not others, use `DSTACK_SERVER_JOB_NETWORK_MODE=1` instead. With this mode, single-node jobs get bridge networking, while distributed tasks still run with host networking. Distributed tasks can then be selectively blocked per project or user by writing a [REST plugin](../reference/plugins/rest/index.md) or a [Python plugin](../reference/plugins/python/index.md).
