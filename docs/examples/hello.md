# Hello, world

This workflow prints `"Hello world"` to the output.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello
        provider: bash
        commands:
          - echo "Hello world"
    ```
