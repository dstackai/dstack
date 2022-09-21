# Deps

If you want your workflow to use artifacts from elsewhere, you can specify the `deps` property. 

[//]: # (There are two general ways to specify a dependency: via tags and via workflow names.)

## Tags

Using tags is the easiest way to reuse artifacts. 

You can assign tags to workflows to reuse their artifacts, or you can upload your own data under a tag.

For example, you can run the [`hello-txt`](artifacts.md) workflow and want to use its artifacts
in another workflows.

First, run the [`hello-txt`](artifacts.md) workflow, and wait until it is finished.

Now, you the name of its run (e.g. `grumpy-zebra-2`)  to add a tag (e.g. `txt-file`):

```shell
dstack tags add txt-file grumpy-zebra-2
```

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

If you want to upload your own data under a tag, instead of the name of the run, you have to 
specify the list of folders that you want to upload via the `--path` argument.

## Workflows

Also, you can reuse artifacts of a workflow from its latest run.  

To do that, just specify the name of the run.

This workflow uses the artifacts of the last run of the `hello-txt` workflow.

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

Note, there should be at least one run of the specified workflow with the status `Done`.
Use the `dstack ps -a` command to see all the recent runs.

[//]: # (External tags and workflows)