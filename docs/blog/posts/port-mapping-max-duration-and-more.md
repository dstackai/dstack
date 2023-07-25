---
title: "dstack 0.10.6: Port mapping, max duration, and more"
date: 2023-07-25
description: The 0.10.6 release introduces port mapping, max duration, more supported GPUs, etc.
slug: "port-mapping-max-duration-and-more"
categories:
- Releases
---

# Port mapping, max duration, and more

__The 0.10.6 release introduces port mapping, max duration, more supported GPUs, etc.__

The latest release of `dstack` brings numerous improvements in many areas: from support for more GPU types to better
mapping of ports and monitoring running workloads. Read below to learn more.

<!-- more -->

## Port mapping

Any task that is running on `dstack` can expose ports. Here's an example:

<div editor-title="serve.dstack.yml"> 

```yaml
type: task

ports:
  - 7860

commands:
  - pip install -r requirements.txt
  - gradio app.py
```

</div>

When you run it with `dstack run`, by default, `dstack` forwards the traffic 
from the specified port to the same port on your local machine.
 
With this update, you now have the option to override the local machine's port for traffic forwarding.

<div class="termy">

```shell
$ dstack run . -f serve.dstack.yml --port 3000:7860
```

</div>

This command forwards the traffic to port `3000` on your local machine.

??? info "Port mapping via .dstack.yml"

    Alternatively, instead of using `--port` in the CLI, you can hardcode the local ports directly 
    into the configuration:

    <div editor-title="serve.dstack.yml"> 

    ```yaml
    type: task
    
    ports:
      - 3000:7860
    
    commands:
      - pip install -r requirements.txt
      - gradio app.py
    ```
    
    </div>

    Now, even without using `--port` with your `dstack run` command, the traffic will be available on port `3000` 
    on your local machine.

If you specify a port on your local machine already taken by another process, dstack will notify you before provisioning cloud resources. 

In summary, port mapping makes it much easier to run tasks on specific ports.

## Max duration

LLM development requires costly GPUs, making cost control crucial. This release simplifies this control by introducing
the `max_duration` configuration.

Previously, when running a dev environment or task with dstack and forgetting about it, it would continue indefinitely.
Now, you can use the `max_duration` property in `.dstack/profiles.yml` to set a maximum time for workloads.

Example:

<div editor-title=".dstack/profiles.yml"> 

```yaml
profiles:
  - name: gcp-t4
    project: gcp
    resources:
      memory: 24GB
      gpu:
        name: T4
    max_duration: 2h
```

</div>

With this profile, `dstack` will automatically stop the workload after 2 hours.

If you don't specify `max_duration`, `dstack` defaults to `6h` for dev environments and `72h` for tasks.

To disable `max duration`, you can set it to `off`.

Imagine the amount of money your team can save with this minor configuration.

## More supported GPUs

With the CUDA version updated to 11.8, `dstack` now supports additional GPU types, including `NVIDIA T4` 
and `NVIDIA L4`. These GPUs are highly efficient for LLM development, offering excellent performance at low costs!

## Examples

Make sure to check the new page with [examples](../../examples/index.md).

The [documentation](../../docs/index.md) is updated to reflect the changes in the release.

## Give it a try

Getting started with `dstack` takes less than a minute. Go ahead and give it a try.

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure,lambda]" -U
$ dstack start
```

</div>
