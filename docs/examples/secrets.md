# Secrets

Secrets can be used to access passwords and tokens securely from workflows (without hard-coding them in the code).

#### Weights & Biases

Here's an example of how to use your Weight & Biases API token in your workflows. 

Go to the settings of your Weight & Biases user and copy your API token. 

Use the `dstack secrets add` command to add it as a secret:

```shell
dstack secrets add WANDB_API_KEY acd0a9e1ebe7a4e4854d2f6a7cef85b5257f8183
```

Now, when you run any workflow, your API token will be passed to the workflow 
via the `WANDB_API_KEY` environment variable:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - pip install wandb
          - wandb login
    ```

Secrets can be managed via the [`dstack secrets`](../reference/cli/secrets.md) command.