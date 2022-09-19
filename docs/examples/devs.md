# Dev environments

The [`code`](../reference/providers/bash.md), [`lab`](../reference/providers/bash.md), and [`notebook`](../reference/providers/bash.md)
providers allow to run code interactively. 

## VS Code

This workflow launches a VS Code dev environment.

It uses the `code` provider.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: ide
        provider: code
    ```

This workflow launches a VS Code dev environment with 1 GPU and 64GB of memory:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: ide-v80
        provider: code
        resources:
          memory: 64GB
          gpu: 1
    ```

## JupyterLab and Jupyter

The `lab` and `notebook` providers work very similarly. Use the same
examples from above and replace the `code` with `lab` or `notebook`.