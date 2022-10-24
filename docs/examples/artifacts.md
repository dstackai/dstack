# Artifacts

The [`bash`](../reference/providers/bash.md), [`code`](../reference/providers/code.md), 
[`lab`](../reference/providers/lab.md), and [`notebook`](../reference/providers/notebook.md) providers 
allow workflows to save output files as artifacts. 

Here's a workflow that creates the `output/hello.txt` file and saves it as an artifact.

```yaml
workflows:
  - name: hello-txt
    provider: bash
    commands:
      - echo "Hello world" > output/hello.txt
    artifacts:
      - path: output 
```

!!! info "NOTE:"
    Artifacts are saved at the end of the workflow.
    They are not saved if the workflow was aborted (e.g. via `dstack stop -x`).

## Access artifacts

To see artifacts of a run, you can use the
[`dstack artifacts list`](../reference/cli/artifacts.md#artifacts-list) command followed
by the name of the run.

```shell
dstack artifacts list grumpy-zebra-1
```

It will list all saved files inside artifacts along with their size:

```shell
PATH  FILE                                  SIZE
data  MNIST/raw/t10k-images-idx3-ubyte      7.5MiB
      MNIST/raw/t10k-images-idx3-ubyte.gz   1.6MiB
      MNIST/raw/t10k-labels-idx1-ubyte      9.8KiB
      MNIST/raw/t10k-labels-idx1-ubyte.gz   4.4KiB
      MNIST/raw/train-images-idx3-ubyte     44.9MiB
      MNIST/raw/train-images-idx3-ubyte.gz  9.5MiB
      MNIST/raw/train-labels-idx1-ubyte     58.6KiB
      MNIST/raw/train-labels-idx1-ubyte.gz  28.2KiB
```

To download artifacts, use the [`dstack artifacts download`](../reference/cli/artifacts.md#artifacts-download) command:

```shell
dstack artifacts download grumpy-zebra-1 .
```

## Mount artifacts

If you want your workflow to save artifacts as you write files to the disk (in real time), 
you can use the `mount` option:

```yaml
workflows:
  - name: hello-sh
    provider: bash
    commands:
      - bash hello.sh
    artifacts:
      - path: output
        mount: true
```

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the cloud storage.

    The `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.