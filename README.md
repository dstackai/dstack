<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="200px"/>    

The easiest way to build AI apps
______________________________________________________________________

[![pypi](https://badge.fury.io/py/dstack.svg)](https://badge.fury.io/py/dstack)
[![stat](https://pepy.tech/badge/dstack)](https://pepy.tech/project/dstack)
[![slack](https://img.shields.io/badge/Slack%20community-purple.svg?logo=slack)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

dstack allows you to train models and run AI apps in your cloud account.

* Define your machine learning tasks as workflows, and run them via the CLI. 
* Specify hardware requirements for your workflows as code.
* Deploy AI applications to dstack with a single command.
* Store, version, and reuse data the most simple way.
* Launch pre-configured development environments with a single command.

This repository contains the open source code of the built-in [providers](providers), the [CLI](src), and [documentation](docs). 

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
```
</details>

Run any workflow in the cloud via a single command:

```bash
$ dstack run train
```

Workflows are optional. You can run providers directly from the CLI:

```bash
dstack run python train.py \
  --dep prepare:latest --artifact checkpoint --gpu 1
```

### Run applications

Here's how to run applications:

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