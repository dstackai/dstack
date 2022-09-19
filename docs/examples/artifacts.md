# Artifacts

If you use the [`bash`](../reference/providers/bash.md), [`code`](../reference/providers/code.md), 
[`lab`](../reference/providers/lab.md), and [`notebook`](../reference/providers/notebook.md) providers, 
you can use the `artifacts` property to specify what folders must be saved as artifacts. 

This workflow creates a `output/hello.txt` and saves it as an artifact.

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

By default, artifacts are saved when the workflow is finished.
Artifacts are not saved if you abort the workflow abruptly using the `dstack stop -x` command.

## Mounting artifacts

If you want, artifact can be mounted directly into filesystem.
In this case all read and write operations will be real-time requests to the cloud storage. 
To use this feature, you have to set the `mount` property of the artifact to `true`.

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

Mounting artifacts may significantly affect performance and thus must be used 
with care.