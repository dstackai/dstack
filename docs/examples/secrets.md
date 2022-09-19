# Secrets

Secrets are stored in the encrypted cloud storage (e.g. for AWS, it's Secrets Manager) 
and can be accessed from running workflows via environment variable.

Secrets can be managed via the [`dstack secrets`](../reference/cli/secrets.md) command.

## Weights & Biases

This example shows how to use secrets to authenticate workflows with Weights & Biases.

First, add the corresponding secret:

```shell
dstack secrets add WANDB_API_KEY acd0a9e1ebe7a4e4854d2f6a7cef85b5257f8183
```

Now, you can run the workflow.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - pip install wandb
          - wandb login
    ```

When you run the workflow, dstack will pass to the `WANDB_API_KEY` environment
variable with the configured API token.