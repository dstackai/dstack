# Resources

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

By default, `dstack` runs workflows locally and utilizes the resources available on your machine.

When you run the workflow in remotely, you can use the `resources` property in your YAML file to specify which 
resources are required by the workflow.

## GPU acceleration

If you run the following workflow remotely, `dstack` will automatically provision a machine with one 
`NVIDIA Tesla V100` GPU:

=== "`.dstack/workflows/resources.yaml`"

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

Go ahead, and run this workflow remotely:

```shell hl_lines="1"
dstack run gpu-v100 --remote
```

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

## Memory

If you run the following workflow remotely, `dstack` will automatically provision a machine with 64GB memory:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: mem-64gb
        provider: bash
        commands:
          - free --giga
        resources:
          memory: 64GB
    ```

Go ahead, and run this workflow remotely:

```shell hl_lines="1"
dstack run mem-64gb --remote
```

## Shared memory

If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

The workflow below uses `16GB` of shared memory:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: shm-size
        provider: bash
        commands:
          - df /dev/shm
        resources:
          shm_size: 16GB 
    ```

Try running this workflow either locally or remotely

```shell hl_lines="1"
dstack run shm-size
```

## Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are 
offered at a significant price discount, and allow to use expensive machines at affordable prices.

If you run the following workflow remotely, `dstack` will automatically provision a spot instance with one default GPU 
(`NVIDIA Tesla K80`):

=== "`.dstack/workflows/resources.yaml`"

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

!!! info "NOTE:"
    If you want to use interruptible instances with your AWS account, make sure to have the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) approved
    by the AWS support team beforehand.
    The approval typically takes a few business days.

## Remote by default

If you plan to run a workflow remotely by default (and don't want to include the `--remote` flag to the `dstack run` command
each time), you can set `remote` to `true` inside `resources`.

This workflow will run remotely by default:

=== "`.dstack/workflows/resources.yaml`"

    ```yaml
    workflows:
      - name: local-hello
        provider: bash
        commands:
          - echo "Hello world"
        resources:
          remote: true
    ```

Go ahead and run it with `dstack run`:

```shell hl_lines="1"
dstack run local-hello
```

## Override via CLI

Resources can be configured not only through the YAML file but
also via the `dstack run` command.

The following command that runs the `hello` workflow remotely using a spot instance with four GPUs:

```shell hl_lines="1"
dstack run hello --remote --gpu 4 --interruptible
```

!!! info "NOTE:"
    To see all supported arguments (that can be used to override resources), 
    use the `dstack run WORKFLOW --help` command.
