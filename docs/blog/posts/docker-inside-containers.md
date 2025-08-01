---
title: "Using Docker and Docker Compose inside GPU-enabled containers"
date: 2024-10-30
description: "The latest release of dstack allows for the direct use of Docker and Docker Compose within run configurations."
image: https://dstack.ai/static-assets/static-assets/images/dstack-docker-inside-containers.png
slug: docker-inside-containers
---

# Using Docker and Docker Compose inside GPU-enabled containers

To run containers with `dstack`, you can use your own Docker image (or the default one) without a need to interact
directly with Docker. However, some existing code may require direct use of Docker or Docker Compose. That's why,
in our latest release, we've added this option.

<div editor-title="examples/misc/docker-compose/task.dstack.yml"> 
    
```yaml 
type: task
name: chat-ui-task

image: dstackai/dind
privileged: true

working_dir: examples/misc/docker-compose
commands:
  - start-dockerd
  - docker compose up
ports: [9000]

resources:
  gpu: 16GB..24GB
```

</div>

<!-- more -->

## How it works

To use Docker or Docker Compose with your `dstack` configuration, set `image` to `dstackai/dind`, `privileged` to 
`true`, and add the `start-dockerd` command. After this command, you can use Docker or Docker Compose directly.


For dev environments, add `start-dockerd` as the first command
in the `init` property.

??? info "Dev environment"
    <div editor-title="examples/misc/docker-compose/.dstack.yml">

    ```yaml
    type: dev-environment
    name: vscode-dind

    image: dstackai/dind
    privileged: true

    ide: vscode
    init:
      - start-dockerd

    resources:
    gpu: 16GB..24GB
    ```

    </div>

The `start-dockerd` script is part of the `dstackai/dind` image, a pre-built image by `dstack` that enables Docker to run
inside containers.

With this setup, you don’t have to worry about configuration—both Docker and Docker Compose work out of the box and
support GPU usage.

!!! info "Backends"
    Note that the `privileged` option is only supported by VM-based backends. This does not include `runpod`, `vastai`, 
    and `kubernetes`. All other backends support it.

## When using it

### docker compose

One of the obvious use cases for this feature is when you need to use Docker Compose. 
For example, the Hugging Face Chat UI requires a MongoDB database, so using Docker Compose to run it is 
the easiest way:

<img src="https://dstack.ai/static-assets/static-assets/images/dstack-docker-compose-terminal.png" width="750"/>

### docker build

Another use case for this feature is when you need to build a custom Docker image using the `docker build` command.

### docker run

Last but not least, you can, of course, use the `docker run` command, for example, if your existing code requires it.

## Examples

A few examples of using this feature can be found in [`examples/misc/docker-compose` :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/blob/master/examples/misc/docker-compose){: target="_ blank"}.

## Feedback

If you find something not working as intended, please be sure to report it to
our [bug tracker :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues){:target="_ blank"}. 
Your feedback and feature requests are also very welcome on both 
[Discord :material-arrow-top-right-thin:{ .external }](https://discord.gg/u8SmfwPpMd){:target="_blank"} and the
[issue tracker :material-arrow-top-right-thin:{ .external }](https://github.com/dstackai/dstack/issues){:target="_blank"}.
