If you use the [`bash`](../reference/providers/bash.md), [`code`](../reference/providers/code.md), 
[`lab`](../reference/providers/lab.md), and [`notebook`](../reference/providers/notebook.md) providers, 
you can specify the hardware requirements for the workflow using the `resources` property.

## GPU acceleration

If you request GPU, the provider pre-installs the CUDA driver for you.

This workflow is using 1 Tesla V100 GPU.

It uses the `nvidia-smi` utility to show GPU information.

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

If you don't specify the name of GPU, dstack will use the cheapest available (e.g. Tesla K80). 

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

Before you can use GPU with your AWS account, the 
corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) has to 
be approved.

## Memory

This workflow is using 64GB of memory.

It uses the standard `free` bash command to show memory information.

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

If your workflow is using parallel communicating processes (e.g. dataloaders in PyTorch), 
you may need to configure the size of the shared memory (`/dev/shm` filesystem) via the `shm_size` property.

This workflow is using `16GB` of shared memory.

It uses the standard `df` bash command to show disk space information.

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

This workflow is using an interruptible instance:

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

Before you can use interruptible instances with your AWS account, the 
corresponding [service quota](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-resource-limits.html) has to 
be approved. 
