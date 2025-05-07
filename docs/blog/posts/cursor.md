---
title: "Accessing dev environments with Cursor"
date: 2025-03-31
description: "TBA"
slug: cursor
image: https://dstack.ai/static-assets/static-assets/images/dstack-cursor-v2.png
categories:
  - Dev environments
---

# Accessing dev environments with Cursor

Dev environments enable seamless provisioning of remote instances with the necessary GPU resources,
automatic repository fetching, and streamlined access via SSH or a preferred desktop IDE.

Previously, support was limited to VS Code. However, as developers rely on a variety of desktop IDEs,
we’ve expanded compatibility. With this update, dev environments now offer effortless access for users of 
[Cursor :material-arrow-top-right-thin:{ .external }](https://www.cursor.com/){:target="_blank"}.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-cursor-v2.png" width="630"/>

<!-- more -->

To access a dev environment via Cursor, set the `ide` property in your configuration to `cursor`.

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
# The name is optional, if not specified, generated randomly
name: vscode

python: "3.11"
# Uncomment to use a custom Docker image
#image: dstackai/base:py3.13-0.7-cuda-12.1

ide: cursor

# Use either spot or on-demand instances
#spot_policy: auto

resources:
  gpu: 24GB
```

</div>

Once you’ve configured the environment, invoke the [`dstack apply`](../../docs/reference/cli/dstack/apply.md) command.
When the dev environment is ready, dstack will provide a URL that you can click to open the environment in your desktop
Cursor IDE.

<div class="termy">

```shell
$ dstack apply -f examples/.dstack.yml

 #  BACKEND  REGION    RESOURCES                SPOT  PRICE
 1  runpod   CA-MTL-1  9xCPU, 48GB, A5000:24GB  yes   $0.11
 2  runpod   EU-SE-1   9xCPU, 43GB, A5000:24GB  yes   $0.11
 3  gcp      us-west4  4xCPU, 16GB, L4:24GB     yes   $0.21

Submit the run vscode? [y/n]: y

Launching `vscode`...
---> 100%

To open in Cursor, use this link:
  cursor://vscode-remote/ssh-remote+vscode/workflow
```

</div>

Clicking the provided URL will prompt your desktop Cursor IDE to automatically connect to the remote machine via the SSH
tunnel created by the `dstack apply` command, allowing you to securely work with your dev environment.

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-cursor-ide.png" width="800"/>

Using Cursor over VS Code offers multiple benefits, particularly when it comes to integrated AI coding assistance and
enhanced developer experience.

!!! info "What's next?"
    1. [Download :material-arrow-top-right-thin:{ .external }](https://www.cursor.com/){:target="_blank"} and install Cursor
    2. Learn more about [dev environments](../../docs/concepts/dev-environments.md), 
       [tasks](../../docs/concepts/tasks.md), [services](../../docs/concepts/services.md),
       and [fleets](../../docs/concepts/fleets.md)
    2. Join [Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"}
