# Secrets

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

Secrets can be used to pass passwords and tokens securely to workflows without hard-coding them in the code.

Secrets can be added via the [`dstack secrets`](../reference/cli/secrets.md) command and accessed from the workflow
via environment variables. 

[//]: # (or in the YAML via `${{ secrets.SECRET_NAME }}` markup.)

## Example

Here's an example of how to use your Weight & Biases API token in your workflows. 

Go to the settings of your Weight & Biases user and copy your API token. 

Use the `dstack secrets add` command to add it as a secret:

<div class="termy">

```shell
$ dstack secrets add WANDB_API_KEY acd0a9d1ebe3a4e4854d2f6a7cef85b5257f8183
```

</div>

Now, when you run any workflow, your API token will be passed to the workflow 
via the `WANDB_API_KEY` environment variable:

<div editor-title=".dstack/workflows/secrets.yaml"> 

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - conda install wandb
      - wandb login
```

</div>

Secrets can be managed via the [`dstack secrets`](../reference/cli/secrets.md#dstack-secrets-add) command.

!!! info "NOTE:"
    Secrets are currently only supported by remote workflows.