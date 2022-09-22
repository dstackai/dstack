# Artifacts

The [`bash`](../reference/providers/bash.md), [`code`](../reference/providers/code.md), 
[`lab`](../reference/providers/lab.md), and [`notebook`](../reference/providers/notebook.md) providers 
allow workflows to save output files as artifacts. 

Here's a workflow that creates the `output/hello.txt` file and saves it as an artifact.

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-txt
        provider: bash
        commands:
          - echo "Hello world" > output/hello.txt
        artifacts:
          - path: output 
    ```

!!! info "NOTE:"
    By default, artifacts are saved when the workflow is finished.
    Artifacts are not saved if you abort the workflow abruptly using the `dstack stop -x` command.

## Mount artifacts

If you want to save artifacts in real time (as you write files to the disk), you can use the `mount` option:

=== ".dstack/workflows.yaml"

    ```yaml
    workflows:
      - name: hello-sh
        provider: bash
        commands:
          - bash hello.sh
        artifacts:
          - path: output
            mount: true
    ```

=== "hello.sh"

    ```bash
    for i in {000..100}
    do
        sleep 1
        echo $i > "output/${i}.txt"
        echo "Wrote output/${i}.txt"
    done
    ```

!!! info "NOTE:"
    Every read or write operation within the mounted artifact directory will create
    an HTTP request to the cloud storage.

    For example, the `mount` option can be used to save and restore checkpoint files
    if the workflow uses interruptible instances.