# Deps

!!! info "NOTE:"
    The source code for the examples below can be found on [GitHub](https://github.com/dstackai/dstack-examples).

By using `deps` workflows can reuse artifacts from other workflows. There are two methods for doing this: by specifying
a workflow or tag name.

## Workflows

The workflow below uses the output artifacts of the most recent run of the `hello-txt` workflow:

=== "`.dstack/workflows/deps.yaml`"

    ```yaml
    workflows:
      - name: cat-txt-2
        provider: bash
        deps:
          - workflow: hello-txt
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    Make sure to run the `hello-txt` workflow beforehand.

## Tags

Tags can be managed using the `dstack tags` command.

You can create a tag either by assigning a tag name to a finished run or by uploading any local data.

Say, you ran the [`hello-txt`](artifacts.md) workflow, and want to reuse its artifacts in another workflow.

Once the [`hello-txt`](artifacts.md) workflow is finished, you can add a tag to it:

```shell hl_lines="1"
dstack tags add txt-file grumpy-zebra-2
```

The `txt-file` here is the name of the tag, and `grumpy-zebra-2` is the run name of the 
[`hello-txt`](artifacts.md) workflow. 

Let's reuse the `txt-file` tag from another workflow:

=== "`.dstack/workflows/deps.yaml`"

    ```yaml
    workflows:
      - name: cat-txt
        provider: bash
        deps:
          - tag: txt-file
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    Tags are only supported for remote runs. If you want to use a tag for a local run, you must first push the 
    artifacts of the local run using the `dstack push` command. 

    You can create also a tag by uploading arbitrary local files. To do this, use the `dstack tags add` command 
    with the `-a PATH` argument, which should point to the local folder containing local files.

## External repos

By default, dstack looks up tags and workflows within the same repo.

If you want to refer to a tag or a workflow from another repo, 
you have to prepend the name (of the tag or the workflow) with the repo name.

The workflow below uses a tag from the `dstackai/dstack` repo:

=== "`.dstack/workflows/deps.yaml`"

    ```yaml
    workflows:
      - name: cat-txt-3
        provider: bash
        deps:
          - workflow: dstackai/dstack/txt-file
        commands:
          - cat output/hello.txt
    ```

!!! info "NOTE:"
    Make sure to run the `hello-txt` workflow in the `dstackai/dstack` repo beforehand.
