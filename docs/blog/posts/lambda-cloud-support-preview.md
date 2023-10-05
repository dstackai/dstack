---
title: "dstack 0.10.3: A preview of Lambda Cloud support"
date: 2023-07-05
description: The new release makes running development environments and tasks in the cloud even easier.
slug: "lambda-cloud-support-preview"
categories:
- Releases
---

# An early preview of Lambda Cloud support

__Check out the 0.10.3 update with initial support for Lambda Cloud.__

`dstack` has two key features. Firstly, it simplifies the running of ML workloads in the cloud.
Secondly, it supports multiple clouds, allowing to stay independent of a particular vendor and reduce
costs. Our latest update represents a significant stride in this direction.

<!-- more -->

## Lambda Cloud

With the 0.10.3 update, `dstack` now allows provisioning infrastructure in Lambda Cloud while storing state and
artifacts in an S3 bucket.

To try the new functionality, you need to install the update and restart the server.

<div class="termy">

```shell
$ pip install "dstack[lambda]" --update
$ dstack start
```

</div>

Once the CLI is updated and the server is restarted, you can configure a Lambda Cloud project.

!!! info "Existing limitations"

    1. Since Lambda Cloud does not have its own object storage, `dstack` requires you to specify an S3 bucket, along with AWS credentials, for storing state and artifacts.
    2. At the moment, there is no possibility to create a Lambda project via the UI. Currently, you can only create a Lambda project through an API request.

See the [Reference](../../docs/reference/backends/lambda.md) for detailed instructions on how to configure a project that uses Lambda Cloud.

## Other changes

The base Docker image of `dstack` includes pre-installed CUDA drivers. However, in certain situations, you may need
to build a custom CUDA kernel, particularly when using libraries like vLLM or TGI.

To address this need, we have pre-configured the base Docker image with the necessary Conda channel. This allows you to
easily install additional CUDA tools like `nvcc` and others.

Here's an example:

<div editor-title=".dstack.yml">

```yaml
type: dev-environment

init:
  - conda install cuda
  - pip install vllm

ide: vscode
```

</div>

!!! info "NOTE:"
    You only need to install `cuda` if you intend to build a custom CUDA kernel. Otherwise, it is not necessary as the
    essential CUDA drivers are already pre-installed.

The [documentation](../../docs/index.md) and [examples](../../examples/index.md)
are updated to reflect the changes.

!!! info "Give it a try and share feedback"
    Go ahead, and install the update, give it a spin, and share your feedback in
    our [Discord community](https://discord.gg/u8SmfwPpMd).
