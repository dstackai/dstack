<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="200px"/>    

Your new home for building AI apps
______________________________________________________________________

[![pypi](https://badge.fury.io/py/dstack.svg)](https://badge.fury.io/py/dstack)
[![stat](https://pepy.tech/badge/dstack)](https://pepy.tech/project/dstack)
[![slack](https://img.shields.io/badge/Slack%20community-purple.svg?logo=slack)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

dstack makes it easy to build AI apps and collaborate.

* You can define common tasks (such as preparing data, training models, running apps, etc.), as workflows 
  and run them in the cloud with one command. 
* The platform automatically saves output artifacts in the cloud, and allow you to version them via tags to reuse and share with others.
* You can configure your own cloud account (e.g. AWS, GCP, Azure, etc.)
* The platform is easily extensible through [providers](providers). Provider add support for
  various languages, training and application frameworks, dev environments, etc.

This repository contains the open source code of the built-in [providers](providers), the [CLI](cli), and [documentation](docs). 

## 📘 Documentation

See full documentation at [docs.dstack.ai](https://docs.dstack.ai)

## 🚀 Getting started

To use dstack, you have to [create an account](https://dstack.ai/signup), and 
obtain your personal token.

### Install the CLI

Here's how to do it:

```bash
pip install dstack
dstack config --token <token> 
```

### Define workflows

Your common project tasks can be defined as workflows:

<details>
<summary>Click to see an example</summary>

```yaml
workflows:
  - name: prepare
    help: "Loads and prepares the training data" 
    provider: python
    file: "prepare.py"
    artifacts: ["data"]

  - name: train
    help: "Trains a model and saves the checkpoints"
    depends-on:
      - prepare:latest
    provider: python
    file: "train.py"
    artifacts: ["checkpoint"]
    resources:
      gpu: 1
      
  - name: app
    help: "Launches an app to play with the model"
    depends-on:
      - train:latest
    provider: streamlit
    target: "app.py"
```
</details>

Run any workflow in the cloud via a single command:

```bash
$ dstack run train
```

For more examples, check out the [examples](examples) folder.

### Run providers

Workflows are optional. You can run providers directly from the CLI:

```bash
dstack run python train.py \
  --dep prepare:latest --artifact checkpoint --gpu 1
```

### Run applications

Here's how to run a Streamlit application:

```bash
dstack run streamlit app.py --dep model:latest
```


### Launch dev environments

If you need an interactive dev environment, you can have it too through the corresponding provider:

```bash
dstack run code app.py --dep prepare:latest --gpu 1
```

This will run a VS Code with mounted artifacts and requested hardware resources.

## 🧩 Providers

Find the full list of built-in providers along examples and their source code [here](providers).

## 🙋‍♀️ Contributing

There are several ways to contribute to dstack:

1. Create pull requests with bugfixes, new providers and examples, and improvements to the docs.
2. Send us links to your own projects that use dstack to be featured here.
3. Report bugs to our [issue tracker](https://github.com/dstackai/dstack/issues).
4. Ask questions and share news within our [Slack community](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ).

Remember, it's important to respect other members of the community. In case you're not sure about the rules, check out [code of conduct](CODE_OF_CONDUCT.md).

## 🛟 Troubleshooting and help

Use our [Slack community](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ) to get help and support.