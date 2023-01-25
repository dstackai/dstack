# Args

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

If you pass any arguments to the `dstack run` command, they can be accessed from the workflow YAML file via
the `${{ run.args }}` expression. 

The workflow below passes workflow arguments to `hello-arg.py`:

=== "`.dstack/workflows/args.yaml`"

    ```yaml
    workflows:
      - name: hello-args
        provider: bash
        commands:
          - python args/hello-arg.py ${{ run.args }}
    ```

=== "`args/hello-arg.py`"

    ```python
    import sys

    if __name__ == '__main__':
        print(sys.argv)
    ```

Run it locally using `dstack run --local` and passing `"Hello, world!"` as an argument:

```shell hl_lines="1"
dstack run hello-arg "Hello, world!"
```

!!! info "NOTE:"
    It supports any arguments except those that are reserved for the [`dstack run`](../reference/cli/index.md#dstack-run) command.