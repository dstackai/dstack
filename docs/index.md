# What is dstack?

dstack is a platform that makes it easy to prepare data, train models, run AI apps, and collaborate.
It allows you to define your common project tasks as workflows, and run them in a configured cloud account.

### Define your workflows

Workflows allow to configure hardware requirements, output artifacts, dependencies to other workflow if any,
and any other parameters supported by the workflow provider.

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

### Run anything from the CLI

You can run workflows or directly providers in the cloud from your terminal.

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

### Version and share artifacts

For every run, output artifacts, e.g. with data, models, or apps, are saved in real-time.

You can use tags to version artifacts, e.g. to reuse them from other workflows or to share them with others.

### Connect your cloud accounts

In order to run workflows or providers, you have to configure your cloud accounts 
by adding the corresponding credentials into dstack settings.