# Hello, world!

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

Create the following workflow YAML file:

<div editor-title=".dstack/workflows/hello.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world!"
```

</div>

## Run locally

To run a workflow locally, simply use the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello

RUN      WORKFLOW  SUBMITTED  STATUS     TAG  BACKENDS
shady-1  hello     now        Submitted       local
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!

$
```

</div>

!!! warning "NOTE:"
    To run workflows locally, it is required to have either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    pre-installed.

## Run remotely

To run a workflow remotely, add the `--remote` flag (or `-r`) to 
the `dstack run` command:

<div class="termy">

```shell
$ dstack run hello --remote

RUN      WORKFLOW  SUBMITTED  STATUS     TAG  BACKENDS
shady-2  hello     now        Submitted       aws
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!

$
```

</div>

!!! info "NOTE:"
    When you run a remote workflow, `dstack` automatically creates resources in the configured cloud,
    and releases them once the workflow is finished.
