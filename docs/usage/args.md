# Args

!!! info "NOTE:"
    The source code of this example is available in the [Playground](../playground.md). 

If you pass any arguments to the `dstack run` command, they can be accessed from the workflow YAML file via
the `${{ run.args }}` expression. 

Create the following Python script:

<div editor-title="usage/args/hello_args.py">

```python
import sys

if __name__ == '__main__':
    print(sys.argv)
```

</div> 

Then, define the following workflow YAML file:

<div editor-title=".dstack/workflows/args.yaml"> 

```yaml
workflows:
  - name: hello-args
    provider: bash
    commands:
      - python usage/args/hello_args.py ${{ run.args }}
```
 
</div>

Run it locally using `dstack run` and passing `"Hello, world!"` as an argument:

<div class="termy">

```shell
$ dstack run hello-args "Hello, world!"
```

</div>

!!! info "NOTE:"
    It supports any arguments except those that are reserved for the [`dstack run`](../reference/cli/run.md) command.