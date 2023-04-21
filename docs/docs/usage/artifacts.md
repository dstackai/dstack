# Artifacts

!!! info "NOTE:"
    The source code of this example is available in the <a href="https://github.com/dstackai/dstack-playground#readme" target="__blank">Playground</a>. 

## Define artifacts

Create the following workflow YAML file:

<div editor-title=".dstack/workflows/artifacts.yaml"> 

```yaml
workflows:
  - name: hello-txt
    provider: bash
    commands:
      - echo "Hello world" > output/hello.txt
    artifacts:
      - path: ./output
```

</div>

Run it locally using `dstack run`:

<div class="termy">

```shell
$ dstack run hello-txt
```

</div>

!!! info "NOTE:"
    Artifacts are saved at the end of the workflow.
    They are not saved if the workflow was aborted (e.g. via `dstack stop -x`).

## List artifacts

To see artifacts of a run, you can use the
[`dstack ls`](../reference/cli/ls.md) command followed
by the name of the run.

<div class="termy">

```shell
$ dstack ls -r grumpy-zebra-1

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

</div>

## Push artifacts

When you run a workflow locally, artifacts are stored in `~/.dstack/artifacts` and can be reused only from the workflows
that run locally too.

If you'd like to reuse the artifacts outside your machine, you must push these artifacts using the 
[`dstack push`](../reference/cli/push.md) command:

<div class="termy">

```shell
$ dstack push grumpy-zebra-1
```

</div>

!!! info "NOTE:"
    If you run a workflow remotely, artifacts are pushed automatically, and it's typically a lot faster
    than pushing artifacts of a local run.

## Pull artifacts

When running a workflow remotely, such as when using `--remote` with the `dstack run` command, the resulting artifacts are
stored remotely. 

If you wish to access these artifacts locally, you can use the [`dstack pull`](../reference/cli/pull.md) command.

<div class="termy">

```shell
$ dstack pull grumpy-zebra-1
```

</div>

This command downloads the artifacts to `~/.dstack/artifacts` and enables their reuse in your other local workflows.

## Add tags

If you wish to reuse the artifacts of a specific run, you can assign a tag (via the [`dstack tags`](../reference/cli/tags.md) command) 
to it and use the tag to reference the artifacts. 

Here's how to add a tag to a run:

<div class="termy">

```shell
$ dstack tags add grumpy-zebra-1 awesome-tag
```

</div>

Even if you delete the `grumpy-zebra-1` run, you can still access its artifacts using the `awesome-tag` tag name. 

You can reference a tag through the [`dstack push`](../reference/cli/push.md),
[`dstack pull`](../reference/cli/pull.md), [`dstack ls`](../reference/cli/ls.md), and through [Deps](deps.md#tags)."

## Real-time artifacts

If you run your workflow remotely, and want to save artifacts in real time (as you write files to the disk), 
you can set the `mount` property to `true` for a particular artifact.

Let's create the following bash script:

<div editor-title="usage/artifacts/hello.sh"> 

```shell
for i in {000..100}
do
    sleep 1
    echo $i > "output/${i}.txt"
    echo "Wrote output/${i}.txt"
done
```

</div>

Now, create the following workflow YAML file:

<div editor-title=".dstack/workflows/resources.yaml"> 

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

</div>

Go ahead and run this workflow remotely:

<div class="termy">

```shell
$ dstack run hello-sh --remote
```

</div>

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the storage.

    The `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.