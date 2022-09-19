# Environment variables

This workflow defines environment variables and prints them to the output. 

It uses the standard `env` bash command to print environment variables. 

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