# Dev environments

The [`code`](../reference/providers/bash.md), [`lab`](../reference/providers/bash.md), and [`notebook`](../reference/providers/bash.md)
providers allow to launch dev environments, such as VS Code, JupyterLab, and Jupyter notebooks.

This is a great way to run code interactively using an IDE, a notebook, or a terminal.

## VS Code

This workflow launches a VS Code dev environment.

```yaml
workflows:
  - name: ide
    provider: code
```

Here's an example if you need 1 GPU and 64GB of RAM.

```yaml
workflows:
  - name: ide-v80
    provider: code
    resources:
      memory: 64GB
      gpu: 1
```

## JupyterLab and Jupyter

You can launch JupyterLab and Jupyter dev environments the very same way – just 
replace `code` with `lab` or `notebook`.