# Environment variables

You can configure environment variables for workflows using the `env` property. 

Here's a workflow that sets `DSTACK_ENV_1`, `DSTACK_ENV_2`, and `DSTACK_ENV_3` environment variables:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-env
        provider: bash
        env:
          - DSTACK_ENV_1=VAL1
          - DSTACK_ENV_2=VAL2
          - DSTACK_ENV_3
        commands:
          - env | grep DSTACK_
    ```