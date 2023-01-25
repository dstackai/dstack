# Dev environments

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

For debugging purposes, you can attach dev environments to your workflows, and run code interactively.

This is especially useful when you're just designing your workflow.

## VS Code

The workflow below launches a VS Code dev environment:

=== "`.dstack/workflows/dev-environments.yaml`"

    ```yaml
    workflows:
      - name: ide-code
        provider: code
    ```

Run it locally using the `dstack run --local` command:

```shell hl_lines="1"
dstack run ide-code --local
```

Once you run it, you'll see the URL to open VS Code in the output:

```shell hl_lines="1"
 RUN               WORKFLOW  SUBMITTED  OWNER           STATUS     TAG
 light-lionfish-1  ide-code  now        peterschmidt85  Submitted

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Web UI available at http://127.0.0.1:51303/?folder=%2Fworkflow&tkn=f2de121b04054f1b85bb7c62b98f2de1
```

Below is a workflow that launches a VS Code but uses one default GPU and 64GB of memory:

=== "`.dstack/workflows/dev-environments.yaml`"

    ```yaml
    workflows:
      - name: ide-code-gpu
        provider: code
        resources:
          memory: 64GB
          gpu: 1
    ```

Run it using the `dstack run` command:

```shell hl_lines="1"
dstack run ide-code-gpu
```

## JupyterLab and Jupyter

You can launch JupyterLab and Jupyter dev environments the very same way, Just replace the `code` provider 
name with `lab` or `notebook`.