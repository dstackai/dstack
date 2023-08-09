---
title: "dstack 0.10.2: Build command, spot and retry policies"
date: 2023-06-22
description: The new release makes running development environments and tasks in the cloud even easier.
slug: "prebuilt-environments-spot-and-retry-policies"
categories:
- Releases
---

# An early preview of the build command

__The 0.10.2 update adds a command that allows for pre-building environments.__

We are continuously striving to make running dev environments and ML tasks in the cloud even easier. With the
new release, we have added two new features that we believe radically improve the developer experience.

<!-- more -->

## Build command

If you use `dstack` for your dev environment or tasks, it includes pre-installed Python and CUDA drivers. However, in most
cases, that's not sufficient. You'll need to install Python libraries, Linux packages, and more.

Usually, this is resolved by using Docker images, but it involves writing Dockerfiles, publishing images via a registry,
and so on. Although Docker images are excellent for production, using them for day-to-day ML development is excessive.
To address this, we've introduced the `dstack build` command.

### Usage example

Consider the following configuration:

<div editor-title=".dstack.yml"> 

```yaml
type: dev-environment
build:
  - apt-get update
  - apt-get install -y ffmpeg
  - pip install -r requirements.txt
ide: vscode
```

</div>

If you run it using `dstack run` and there is no pre-built image available for this configuration, it will fail and prompt
you to either use the `dstack build` command or add the `--build` flag to the `dstack run` command.
If the pre-built image is available, it will be used automatically.

Now, if your setup is complex or time-consuming, you don't necessarily have to build and publish your own Docker images.
You can simply define the build property and use the `dstack build` command or add the `--build` flag to the `dstack run`
command.

If you have specific commands that need to be executed before the dev environment starts, you can now use
the `init` property in YAML.

You can find more details on the updated syntax of `.dstack.yml` in the [Reference](../../docs/reference/dstack.yml/index.md)
section.

## Spot and retry policies

Another new major feature is support for `spot_policy` and `retry_policy` in `.dstack/profiles.yml`.

### Spot policy

The `spot_policy` determines if `dstack` should use spot or on-demand cloud instances for running dev environments and
tasks. It can be set to the following values:

- `spot` – Always uses spot cloud instances only
- `on-demand` – Always uses on-demand cloud instances only
- `auto` – Try to use spot cloud instances if available and on-demand if not

If you don't specify `spot_policy`, it is set to `on-demand` by default for dev environments, while for tasks,
the default is `auto`.

### Retry policy

The `retry_policy` determines if `dstack` should retry when there is no cloud capacity for running the dev environment or
task. It can have the following nested properties:

- `retry` – `true` if `dstack` should retry, and `false` if not
- `limit` – The duration within which `dstack` should retry. The default is `1d` (one day).

If you don't specify the `retry_policy`, it is enabled for tasks by default, while for dev environments, it is disabled.

You can find more details on the updated syntax of `.dstack/profiles.yml` in the [Reference](../../docs/reference/profiles.yml.md) section.

With these introduced policies, using spot cloud instances becomes easier. Additionally, you can now schedule tasks that
utilize on-demand instances. This is particularly useful when there is limited capacity in a specific region and you
want the task to automatically run once the capacity becomes available.

## Other changes

Other improvements in this release:

- For GCP, it now checks if your cloud account has the necessary permissions to edit project backend settings. 
- Deletion of repositories is now possible through the UI. 
- When running a dev environment from a Git repo, you can now pull and push changes directly from the dev environment,
  with `dstack` correctly configuring your Git credentials.
- The newly added Python API for working with artifacts is now documented [here](../../docs/reference/api/python.md).

The [documentation](../../docs) and [examples](https://github.com/dstackai/dstack-examples/blob/main/README.md)
are updated to reflect the changes.

!!! info "Give it a try and share feedback"
    Go ahead, and install the update, give it a spin, and share your feedback in
    our [Slack community](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

