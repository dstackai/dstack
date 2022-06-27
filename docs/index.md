# What is dstack?

dstack is a platform that makes it very easy to build and share AI apps.
It allows you to prepare data, train models, run AI apps, and collaborate within one 
simple yet extensible platform.

### Workflows

Define common tasks as workflows and run them locally or in the cloud. 
Configure output artifacts, hardware requirements, and dependencies to other workflow if any.

=== ".dstack/workflows.yaml"
    ```yaml
    workflows:
      - name: prepare
        provider: python
        file: "prepare.py"
        artifacts: ["data"]
    
      - name: train
        depends-on:
          - prepare:latest
        provider: python
        file: "train.py"
        artifacts: ["checkpoint"]
        resources:
          gpu: 4
          
      - name: app
        depends-on:
          - train:latest
        provider: streamlit
        target: "app.py"
    ```

### Run command

Run workflows, providers, and apps locally or in the cloud with single command from your terminal.

For every run, local or remote, dstack mounts your local repository with local changes, artifacts from dependencies, and track logs and output artifacts in real-time.

#### Workflows

Here's how to run a workflow:

```bash
$ dstack run train \
  --epoch 100 --seed 2 --batch-size 128

RUN         WORKFLOW  PROVIDER  STATUS     APP     ARTIFACTS  SUBMITTED  TAG                    
nice-fox-1  train     python    SUBMITTED  <none>  <none>     now        <none>

$ █
```

#### Providers

As an alternative to workflows, you can run any providers directly: 

```bash
$ dstack run python train.py \
  --epoch 100 --seed 2 --batch-size 128 \
  --depends-on prepare:latest --artifact checkpoint --gpu 1

RUN         WORKFLOW  PROVIDER  STATUS     APP     ARTIFACTS   SUBMITTED  TAG                    
nice-fox-1  <none>    python    SUBMITTED  <none>  checkpoint  now        <none>

$ █
```

#### Applications

Some providers allow to launch interactive applications, including [JupyterLab](https://github.com/dstackai/dstack/tree/master/providers/lab/#readme),
[VS Code](https://github.com/dstackai/dstack/tree/master/providers/code/#readme), 
[Streamlit](https://github.com/dstackai/dstack/tree/master/providers/streamlit/#readme), 
[Gradio](https://github.com/dstackai/dstack/tree/master/providers/gradio/#readme), 
[FastAPI](https://github.com/dstackai/dstack/tree/master/providers/fastapi/#readme), or
anything else.

Here's an example of the command that launches a VS Code application:

```bash
$ dstack run code \
    --artifact output \
    --gpu 1

RUN         WORKFLOW  PROVIDER  STATUS     APP   ARTIFACTS  SUBMITTED  TAG                    
nice-fox-1  <none>    code      SUBMITTED  code  output     now        <none>

$ █
```
!!! info "Supported providers"
    You are welcome to use a variety of the [built-in providers](https://github.com/dstackai/dstack/tree/master/providers/#readme), 
    or the providers from the community.

### Artifacts and tags

For every run, output artifacts, e.g. with data, models, or apps, are saved in real-time.

Use tags to version artifacts to reuse them from other workflows or to share them with others.

### Multi-cloud

You can configure and use your own cloud accounts, such as AWS, GCP, or Azure, to run workflows,
providers and applications.