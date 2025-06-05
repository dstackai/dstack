---
title: Auto-shutdown for inactive dev environments—no idle GPUs
date: 2025-02-19
description: "dstack introduces a new feature that automatically detects and shuts down inactive dev environments, helping you avoid wasted GPU costs."  
slug: inactivity-duration
image: https://dstack.ai/static-assets/static-assets/images/inactive-dev-environments-auto-shutdown.png
categories:
  - Dev environments
---

# Auto-shutdown for inactive dev environments—no idle GPUs

Whether you’re using cloud or on-prem compute, you may want to test your code before launching a
training task or deploying a service. `dstack`’s [dev environments](../../docs/concepts/dev-environments.md)
make this easy by setting up a remote machine, cloning your repository, and configuring your IDE —all within 
a container that has GPU access.

One issue with dev environments is forgetting to stop them or closing your laptop, leaving the GPU idle and costly. With
our latest update, `dstack` now detects inactive environments and automatically shuts them down, saving you money.

<img src="https://dstack.ai/static-assets/static-assets/images/inactive-dev-environments-auto-shutdown.png" width="630"/>

<!-- more -->

When defining a dev environment, you can now enable automatic shutdown by setting the
`inactivity_duration` property to specify how long `dstack` should wait before 
automatically terminating an inactive environment.

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode

python: "3.11"

ide: vscode

# Shut-down if inactive for 2 hours
inactivity_duration: 2h

resources:
  gpu: 1
```

A dev environment is considered inactive when you close your desktop VS Code, exit any `ssh <run name>` sessions, or
interrup the `dstack apply` or `dstack attach` command. 

If you go offline without manually stopping anything, `dstack` will
automatically detect inactivity and shut down the environment within approximately three minutes.

If you’ve configured `inactivity_duration`, you can check how long a dev environment environment has been inactive using:

<div class="termy">

```shell
$ dstack ps --verbose
 NAME    BACKEND  RESOURCES       PRICE    STATUS                 SUBMITTED
 vscode  cudo     2xCPU, 8GB,     $0.0286  running                8 mins ago
                  100.0GB (disk)           (inactive for 2m 34s)
```

</div>

Reattaching to the environment with [`dstack attach`](../../docs/reference/cli/dstack/attach.md)
resets the inactivity timer within seconds.

Overall, the new feature makes using dev environments both safer and more cost-effective.
This not only helps reduce unnecessary GPU costs, but also ensures more efficient reuse of 
fleets by teams.

!!! info "What's next?"
    1. Check [dev environments](../../docs/concepts/dev-environments.md), 
       [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md),
       and [fleets](../../docs/concepts/fleets.md)
    2. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
