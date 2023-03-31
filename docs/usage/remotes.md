# Remotes

!!! info "NOTE:"
    The source code of this example is available in the [Playground](../playground.md). 

By default, workflows run locally. To run workflows remotely, you need to first configure a remote using the [`dstack
config`](../reference/cli/config.md) command. 

<div class="termy">

```shell
$ dstack config
```

</div>

!!! info "NOTE:"
    To use AWS or GCP as a remote, the corresponding cloud credentials must be
    configured locally.

Once a remote is configured, use the `--remote` flag with the `dstack run` command to run a workflow in
the remote.

<div class="termy">

```shell
$ dstack run hello --remote
```

</div>

## Resources

When running a workflow remotely, you can specify which [resources](../reference/providers/bash.md#resources) to use, such as GPU and memory.

### GPU

If you run the following workflow remotely, `dstack` will automatically provision a machine with one 
`NVIDIA Tesla V100` GPU:

<div editor-title=".dstack/workflows/resources.yaml">

```yaml hl_lines="7 8 9"
workflows:
  - name: gpu-v100
    provider: bash
    commands:
      - nvidia-smi
    resources:
      gpu:
        name: V100
        count: 1
```

</div>

Go ahead, and run this workflow remotely:

<div class="termy">

```shell
$ dstack run gpu-v100 --remote
```

</div>

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

### Memory

If you run the following workflow remotely, `dstack` will automatically provision a machine with 64GB memory:

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml hl_lines="7"
workflows:
  - name: mem-64gb
    provider: bash
    commands:
      - free --giga
    resources:
      memory: 64GB
```

</div>

Go ahead, and run this workflow remotely:

<div class="termy">

```shell
$ dstack run mem-64gb --remote
```

</div>

### Shared memory

If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

The workflow below uses `16GB` of shared memory:

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml hl_lines="7"
workflows:
  - name: shm-size
    provider: bash
    commands:
      - df /dev/shm
    resources:
      shm_size: 16GB 
```

</div>

Try running this workflow either locally or remotely:

<div class="termy">

```shell
$ dstack run shm-size
```

</div>

## Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are 
offered at a significant price discount, and allow to use expensive machines at affordable prices.

If you run the following workflow remotely, `dstack` will automatically provision a spot instance with one default GPU 
(`NVIDIA Tesla K80`):

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml hl_lines="7 8"
workflows:
  - name: gpu-i
    provider: bash
    commands:
      - nvidia-smi
    resources:
      interruptible: true
      gpu: 1
```

</div>

!!! info "NOTE:"
    If you want to use interruptible instances with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

## Remote by default

If you plan to run a workflow remotely by default (and don't want to include the `--remote` flag to the `dstack run` command
each time), you can set `remote` to `true` inside `resources`.

This workflow will run remotely by default:

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml hl_lines="7"
workflows:
  - name: local-hello
    provider: bash
    commands:
      - echo "Hello world"
    resources:
      remote: true
```

</div>

Go ahead and run it with `dstack run`:

<div class="termy">

```shell
$ dstack run local-hello
```

</div>

## Override via CLI

Resources can be configured not only through the YAML file but
also via the `dstack run` command.

The following command that runs the `hello` workflow remotely using a spot instance with four GPUs:

<div class="termy">

```shell
$ dstack run hello --remote --gpu 4 --interruptible
```

</div>

!!! info "NOTE:"
    To see all supported arguments (that can be used to override resources), 
    use the `dstack run WORKFLOW --help` command.
