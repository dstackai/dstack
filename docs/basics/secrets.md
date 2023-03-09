# Secrets

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

Secrets can be used to access passwords and tokens securely from remote workflows (without hard-coding them in the code).

## Example

Here's an example of how to use your Weight & Biases API token in your workflows. 

Go to the settings of your Weight & Biases user and copy your API token. 

Use the `dstack secrets add` command to add it as a secret:

```shell hl_lines="1"
dstack secrets add WANDB_API_KEY acd0a9d1ebe3a4e4854d2f6a7cef85b5257f8183
```

Now, when you run any workflow, your API token will be passed to the workflow 
via the `WANDB_API_KEY` environment variable:

=== "`.dstack/workflows/secrets.yaml`"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - conda install wandb
          - wandb login
    ```

Secrets can be managed via the [`dstack secrets`](../reference/cli/secrets.md#dstack-secrets-add) command.

!!! info "NOTE:"
    Secrets are currently only supported by remote workflows.

[//]: # (TODO: Align secrets with local and remote workflows)
