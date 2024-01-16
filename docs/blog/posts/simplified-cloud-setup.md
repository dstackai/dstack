---
date: 2023-10-18
description: "The latest update makes it much easier to configure clouds and enhances the Python API."
slug: "simplified-cloud-setup"
categories:
- Releases
---

# dstack 0.12.0: Simplified cloud setup, and refined API

__The latest update simplifies cloud configuration and enhances the Python API.__

For the past six weeks, we've been diligently overhauling `dstack` with the aim of significantly simplifying the process
of configuring clouds and enhancing the functionality of the API. Please take note of the breaking
changes, as they necessitate careful migration.

<!-- more -->

## Cloud setup

Previously, the only way to configure clouds for a project was through the UI. Additionally, you had to specify not only
the credentials but also set up a storage bucket for each cloud to store metadata.

Now, you can configure clouds for a project via `~/.dstack/server/config.yml`. Example:

<div editor-title="~/.dstack/server/config.yml">

```yaml
projects:
- name: main
  backends:
  - type: aws
    creds:
      type: access_key
      access_key: AIZKISCVKUKO5AAKLAEH
      secret_key: QSbmpqJIUBn1V5U3pyM9S6lwwiu8/fOJ2dgfwFdW
```

</div>

Regions and other settings are optional. Learn more on what credential types are supported 
via [Clouds](../../docs/config/server.md).

## Enhanced API

The earlier introduced Python API is now greatly refined.

Creating a `dstack` client is as easy as this: 

```python
from dstack.api import Client, ClientError

try:
    client = Client.from_config()
except ClientError:
    print("Can't connect to the server")
```

Now, you can submit a task or a service:

```python
from dstack.api import Task, Resources, GPU

task = Task(
    image="ghcr.io/huggingface/text-generation-inference:latest",
    env={"MODEL_ID": "TheBloke/Llama-2-13B-chat-GPTQ"},
    commands=[
        "text-generation-launcher --trust-remote-code --quantize gptq",
    ],
    ports=["80"],
)

run = client.runs.submit(
    run_name="my-awesome-run",
    configuration=task,
    resources=Resources(gpu=GPU(memory="24GB")),
)
```

The `dstack.api.Run` instance provides methods for various operations including attaching to the run, 
forwarding ports to `localhost`, retrieving status, stopping, and accessing logs. For more details, refer to 
the [example](../../examples/deploy-python.md) and [reference](../../docs/reference/api/python/index.md).

## Other changes

- Because we've prioritized CLI and API UX over the UI, the UI is no longer bundled. 
Please inform us if you experience any significant inconvenience related to this.
- Gateways should now be configured using the `dstack gateway` command, and their usage requires you to specify a domain.
  Learn more about how to [set up a gateway](../../docs/concepts/services.md#set-up-a-gateway).
- The `dstack start` command is now `dstack server`.
- The Python API classes were moved from the `dstack` package to `dstack.api`.

## Migration

Unfortunately, when upgrading to 0.12.0, there is no automatic migration for data.
This means you'll need to delete `~/.dstack` and configure `dstack` from scratch.

1. `pip install "dstack[all]==0.12.0"`
2. Delete `~/.dstack`
3. Configure clouds via `~/.dstack/server/config.yml` (see the [new guide](../../docs/config/server.md))
4. Run `dstack server`

The [documentation](../../docs/index.md) and [examples](../../examples/index.md) are updated.

## Give it a try

Getting started with `dstack` takes less than a minute. Go ahead and give it a try.

<div class="termy">

```shell
$ pip install "dstack[all]" -U
$ dstack server
```
</div>

!!! info "Feedback and support"
    Questions and requests for help are very much welcome in our 
    [Discord server](https://discord.gg/u8SmfwPpMd).