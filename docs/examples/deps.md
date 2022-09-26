# Deps

Deps allow workflows to reuse artifacts via tags or from other workflows.

## Tags

The easiest way to create a tag is to add a tag to a finished run. 

For example, you ran the [`hello-txt`](artifacts.md) workflow, and want to use its artifacts in another workflow.

Once the [`hello-txt`](artifacts.md) workflow is finished, you can add a tag to it:

```shell
dstack tags add txt-file grumpy-zebra-2
```

The `txt-file` here is the name of the tag, and `grumpy-zebra-2` is the run name of the [`hello-txt`](artifacts.md) workflow. 

Now you can use this tag from another workflow:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: cat-txt
        provider: bash
        deps:
          - tag: txt-file
        commands:
          - cat output/hello.txt
    ```

!!! tip "NOTE:"
    One more way to create a tag is by uploading local files as tag artifacts. 
    See the [`dstack tags add`](../reference/cli/tags.md#tags-add) command documentation to know more.

## Workflows

Another way to reuse artifacts of a workflow is via the name of the workflow.
This way, dstack will use artifacts of the last run with that name.

Here's a a workflow that uses artifacts of the last run of the `hello-txt` workflow.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: cat-txt
        provider: bash
        deps:
          - workflow: hello-txt
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    There should be at least one run of the `hello-txt` workflow in the `DONE` status.

## External repos

By default, dstack looks up tags and workflows within the current Git repo only.

If you want to refer to a tag or a workflow from another Git repo, 
you have to prepend the name (of the tag or the workflow) with the repo name.

Here's a workflow that refers to a tag from the `dstackai/dstack` Git repo.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: cat-txt
        provider: bash
        deps:
          - tag: dstackai/dstack/txt-file
        commands:
          - cat output/hello.txt
    ```