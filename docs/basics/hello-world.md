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

## Run locally

To run a workflow locally, simply use the `dstack run` command:

```shell hl_lines="1"
dstack run hello
```

You'll see the output in real-time:

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
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

This will automatically set up the necessary infrastructure (e.g. within a 
configured cloud account), run the workflow, and upon completion, tear down 
the infrastructure.

```shell hl_lines="1"
RUN           WORKFLOW  SUBMITTED  OWNER           STATUS     TAG 
slim-shady-1  hello     now        peterschmidt85  Submitted  
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world!
```

!!! info "NOTE:"
    You can use `pip`, `conda`, and `python` executables from the `commands` property of your workflow.
    See [Python](python.md) for more details.