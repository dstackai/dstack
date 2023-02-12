# Hello, world!

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

The workflow below prints `"Hello, world"`.

=== "`.dstack/workflows/hello.yaml`"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - echo "Hello, world!"
    ```

!!! info "NOTE:"
    You can use `pip`, `conda`, and `python` executables within workflows.
    See [Python](python.md) and [Conda](conda.md) for more details.

## Run locally

To run a workflow locally, simply use the `dstack run` command:

```shell hl_lines="1"
dstack run hello
```

You'll see the output in real-time:

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG  BACKENDS
slim-shady-1  hello     now        peterschmidt85  Submitted       local
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

!!! warning "NOTE:"
    To run workflows locally, it is required to have either Docker or [NVIDIA Docker](https://github.com/NVIDIA/nvidia-docker) 
    pre-installed.

## Run remotely

To run a workflow remotely, add the `--remote` flag (or `-r`) to 
the `dstack run` command:

```shell hl_lines="1"
dstack run hello --remote
```

!!! info "NOTE:"
    When you run a remote workflow, `dstack` automatically creates resources in the configured cloud,
    and releases them once the workflow is finished.

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG  BACKENDS
slim-shady-1  hello     now        peterschmidt85  Submitted       aws
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```
