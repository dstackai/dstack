# What is dstack?

dstack is a platform that makes it very easy to manage data, train models, build and deploy AI apps.

### Organize your workflows

dstack allows you to define your common tasks as workflows, and run them in a configured cloud account.

You can configure hardware requirements, output artifacts, dependencies to other workflow if any,
and any other parameters supported by the workflow provider.

???- info "Click to see an example"

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

### Run workflows, providers, and apps

You can run workflows or directly providers in the cloud from your terminal.

Here's how to run a workflow:

```bash
dstack run train \
  --epoch 100 --seed 2 --batch-size 128
```

As an alternative to workflows, you can run any providers directly: 

```bash
dstack run python train.py \
  --epoch 100 --seed 2 --batch-size 128 \
  --dep prepare:latest --artifact checkpoint --gpu 1
```

Some providers allow to launch interactive applications, including [JupyterLab](https://github.com/dstackai/dstack/tree/master/providers/lab/#readme),
[VS Code](https://github.com/dstackai/dstack/tree/master/providers/code/#readme), 
[Streamlit](https://github.com/dstackai/dstack/tree/master/providers/streamlit/#readme), 
[Gradio](https://github.com/dstackai/dstack/tree/master/providers/gradio/#readme), 
[FastAPI](https://github.com/dstackai/dstack/tree/master/providers/fastapi/#readme), or
anything else.

Here's an example of the command that launches a VS Code application:

```bash
dstack run code \
  --artifact output \
  --gpu 1
```
### Providers registry

You are welcome to use a variety of the [built-in providers](https://github.com/dstackai/dstack/tree/master/providers/#readme), 
or the providers from the community.

<div class="grid cards" markdown>

-  __python__

    Runs a Python script

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/python/#readme)

- __docker__

    Runs a Docker image
    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/docker/#readme)

- __streamlit__

    Runs a Streamlit app

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/streamlit/#readme)

- __gradio__

    Runs a Gradio app

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/gradio/#readme)

- __fastapi__

    Runs a FastAPI app

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/fastapi/#readme)

- __lab__

    Runs a JupyterLab app

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/lab/#readme)

- __code__

    Runs a VS Code app

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/code/#readme)

- __notebook__

    Runs a Jupyter notebook

    [:octicons-arrow-right-24: Reference](https://github.com/dstackai/dstack/tree/master/providers/notebook/#readme)

</div>

### Share data, models, and apps

For every run, output artifacts, e.g. with data, models, or apps, are saved in real-time.

You can use tags to version artifacts, e.g. to reuse them from other workflows or to share them with others.

### Connect your cloud accounts

In order to run workflows or providers, you have to configure your cloud accounts 
by adding the corresponding credentials into dstack settings.