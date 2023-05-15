# Resources

When running a workflow in the cloud, you can specify which [resources](../reference/providers/bash.md#resources) to use,
such as GPU and memory.

## GPU

If you run the following workflow remotely, `dstack` will automatically provision a machine with one
`NVIDIA Tesla V100` GPU:

<div editor-title=".dstack/workflows/resources.yaml">

```yaml
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

Go ahead, and run this workflow:

<div class="termy">

```shell
$ dstack run gpu-v100
```

</div>

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure to have the
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

## Memory

If you run the following workflow remotely, `dstack` will automatically provision a machine with 64GB memory:

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml
workflows:
  - name: mem-64gb
    provider: bash
    commands:
      - free --giga
    resources:
      memory: 64GB
```

</div>

Go ahead, and run this workflow:

<div class="termy">

```shell
$ dstack run mem-64gb
```

</div>

## Shared memory

If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch),
you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

The workflow below uses `16GB` of shared memory:

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml
workflows:
  - name: shm-size
    provider: bash
    commands:
      - df /dev/shm
    resources:
      shm_size: 16GB 
```

</div>

Try running this workflow:

<div class="termy">

```shell
$ dstack run shm-size
```

</div>

## Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are
offered at a significant price discount, and allow to use expensive machines at affordable prices.

If you run the following workflow in the cloud, `dstack` will automatically provision a spot instance with one default
GPU (`NVIDIA Tesla K80`):

<div editor-title=".dstack/workflows/resources.yaml"> 

```yaml
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

## Override via CLI

Resources can be configured not only through the YAML file but
also via the `dstack run` command.

The following command that runs the `hello` workflow remotely using a spot instance with four GPUs:

<div class="termy">

```shell
$ dstack run hello --gpu 4 --interruptible
```

</div>

!!! info "NOTE:"
    To see all supported arguments (that can be used to override resources),
    use the `dstack run WORKFLOW --help` command.
