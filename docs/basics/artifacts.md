# Artifacts

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

## Define artifacts

The workflow below creates the `output/hello.txt` file and saves it as an artifact:

=== "`.dstack/workflows/artifacts.yaml`"

    ```yaml
    workflows:
      - name: hello-txt
        provider: bash
        commands:
          - echo "Hello world" > output/hello.txt
        artifacts:
          - path: ./output
    ```

Run it locally using `dstack run`:

```shell hl_lines="1"
dstack run hello-txt
```

!!! info "NOTE:"
    Artifacts are saved at the end of the workflow.
    They are not saved if the workflow was aborted (e.g. via `dstack stop -x`).

## List artifacts

To see artifacts of a run, you can use the
[`dstack ls`](../reference/cli/ls.md) command followed
by the name of the run.

```shell hl_lines="1"
dstack ls grumpy-zebra-1
```

It will list all saved files inside artifacts along with their size:

```shell hl_lines="1"
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

## Push artifacts to the cloud

When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and can be reused only from the workflows
that run locally too.

If you'd like to reuse the artifacts outside your machine, you must push these artifacts using the `dstack push` command:

```shell hl_lines="1"
dstack push grumpy-zebra-1
```

!!! info "NOTE:"
    If you run a workflow remotely, artifacts are pushed automatically, and it's typically a lot faster
    than pushing artifacts of a local run.

## Real-time artifacts

If you run your workflow remotely, and want to save artifacts in real time (as you write files to the disk), 
you can set the `mount` property to `true` for a particular artifact.

The workflow below creates files in `output` and save them as artifacts in real-time:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: hello-sh
        provider: bash
        commands:
          - bash artifacts/hello.sh
        artifacts:
          - path: ./output
            mount: true
    ```

=== "`artifacts/hello.sh`"

    ```shell
    for i in {000..100}
    do
        sleep 1
        echo $i > "output/${i}.txt"
        echo "Wrote output/${i}.txt"
    done
    ```

Go ahead and run this workflow remotely:

```shell
dstack run hello-sh --remote
```

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the storage.

    The `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.