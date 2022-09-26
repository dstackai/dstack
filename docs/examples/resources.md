The [`bash`](../reference/providers/bash.md), [`code`](../reference/providers/code.md), 
[`lab`](../reference/providers/lab.md), and [`notebook`](../reference/providers/notebook.md) providers 
allow workflows to specify required compute resources.

## GPU acceleration

If you request GPU, the provider pre-installs the CUDA driver for you.

Let's create a workflow that uses a Tesla V100 GPU.

=== ".dstack/workflows.yaml"

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

If you don't specify the name of GPU, dstack will use the cheapest available GPU (e.g. Tesla K80). 

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: gpu-1
        provider: bash
        commands:
          - nvidia-smi
        resources:
          gpu: 1
    ```

!!! info "NOTE:"
    If you want to use GPU with your AWS account, make sure the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) is approved.

## Memory

Here's an example of a workflow that requires 64GB of RAM.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: gpu-v100
        provider: bash
        commands:
          - free -m
        resources:
          memory: 64GB
    ```

## Shared memory

!!! info "NOTE:"
    If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
    you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

Here's a workflow that uses `16GB` of shared memory.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: shm-size
        provider: bash
        commands:
          - df /dev/shm
        resources:
          shm_size: 16GB 
    ```

## Interruptible instances

Interruptible instances (also known as spot instances or preemptive instances) are 
not guaranteed and may be interrupted by the cloud provider at any time.
Because of that, they are typically several times cheaper.

Interruptible instances can be a great way to use expensive GPU at affordable prices.

Here's an example of a workflow that uses an interruptible instance:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-i
        provider: bash
        commands:
          - echo "Hello world"
        resources:
          interruptible: true
    ```

!!! info "NOTE:"
    If you want to use interruptible instances with your AWS account, make sure the 
    corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) is approved.