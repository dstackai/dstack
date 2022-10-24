# Hello, world

Let's start from the very beginning: a workflow that prints `"Hello, world"`.  

Go ahead, and create the `.dstack/workflows.yaml` file in your project directory:

```yaml
workflows:
  - name: hello
    provider: bash
    commands:
      - echo "Hello, world"
```

Now, use the `dstack run` command to run it:

```shell
dstack run hello
```

You'll see the output in real-time as your workflow is running:

```shell
RUN           WORKFLOW  STATUS     APPS  ARTIFACTS  SUBMITTED  TAG 
slim-shady-1  hello     Submitted                   now 
 
Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

Hello, world
```

That was simple, wasn't it? Let's try something a bit more interesting.