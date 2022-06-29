<div align="center">
<img src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg" width="200px"/>    

Your new home for building AI apps
______________________________________________________________________

[![pypi](https://badge.fury.io/py/dstack.svg)](https://badge.fury.io/py/dstack)
[![stat](https://pepy.tech/badge/dstack)](https://pepy.tech/project/dstack)
[![slack](https://img.shields.io/badge/Join%20Slack%20channel-grey.svg?logo=slack)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

[//]: # ([![twitter]&#40;https://img.shields.io/twitter/follow/dstackai.svg?style=social&label=Follow&#41;]&#40;https://twitter.com/dstackai&#41;)

</div>

## Overview

dstack is a platform that makes it easy to prepare data, train models, run AI apps, and collaborate.
Define workflows as code, and run against a configured cloud account.

### Define your workflows

Define common tasks as workflows and run them in the cloud. 
Configure output artifacts, hardware requirements, and dependencies to other workflow if any.

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

Run workflows, providers, and apps in the cloud with single command from your terminal.

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

### Version and share artifacts

For every run, output artifacts, e.g. with data, models, or apps, are saved in real-time.

Use tags to version artifacts to reuse them from other workflows or to share them with others.

### Connect your cloud accounts

You can configure and use your own cloud accounts, such as AWS, GCP, or Azure, to run workflows,
providers and applications.

## Repository

This repository contains dstack's open-source and public code, documentation, and other key resources:

* [`providers`](providers): The source code of the built-in dstack workflow providers
* [`cli`](cli): The source code of the dstack CLI pip package
* [`docs`](docs): A user guide to the whole dstack platform ([docs.dstack.ai](https://docs.dstack.ai))

Here's the list of other packages that are expected to be included into this repository with their source code soon:

* `runner`: The source code of the program that runs dstack workflows
* `server`: The source code of the program that orchestrates dstack runs and jobs and provides a user interface
* `examples`: The source code of the examples of using dstack

## Contributing

Please check [CONTRIBUTING.md](CONTRIBUTING.md) if you'd like to get involved in the development of dstack.

## License

Please see [LICENSE.md](LICENSE.md) for more information about the terms under which the various parts of this repository are made available.

## Contact

Find us on Twitter at [@dstackai](https://twitter.com/dstackai), join our [Slack community](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ) for quick help and support.

Project permalink: `https://github.com/dstackai/dstack`
