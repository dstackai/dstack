<div align="center">
<h1 align="center">
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo.svg" width="400px"/>
    </picture>
  </a>
</h1>

<h4 align="center">
ML workflows as code
</h4>

<p align="center">
The easiest way to run ML workflows on any cloud platform 
</p>

[![Slack](https://img.shields.io/badge/slack-join%20chat-blueviolet?logo=slack&style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)

<p align="center">
<a href="https://dstack.ai/docs/quick-start" target="_blank"><b>Quick start</b></a> • 
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> • 
<a href="https://dstack.ai/tutorials/dolly" target="_blank"><b>Tutorials</b></a> •
<a href="https://dstack.ai/blog" target="_blank"><b>Blog</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)

</div>

## What is dstack?

`dstack` makes it very easy to define ML workflows
and run them on any cloud platform. It provisions infrastructure,
manages data, and monitors usage for you.

Ideal for processing data, training models, running apps, and any other ML development tasks.

## Installation and setup

To use `dstack`, install it with `pip` and start the Hub application.

```shell
pip install dstack
dstack start
```

The `dstack start` command starts the Hub application, and creates the default project to run workflows locally.

If you'll want to run workflows in the cloud (e.g. AWS, or GCP), simply log into the Hub application, and 
create a new project.

## Run your first  workflows

Let's define our first ML workflow in `.dstack/workflows/hello.yaml`:

```yaml
workflows:
  - name: train-mnist
    provider: bash
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python examples/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
```

The YAML file allows you to request hardware [resources](https://dstack.ai/docs/usage/resources), run [Python](https://dstack.ai/docs/usage/python),
save [artifacts](https://dstack.ai/docs/usage/artifacts), use [cache](https://dstack.ai/docs/usage/cache) and  
[dependencies](https://dstack.ai/docs/usage/deps), create [dev environments](https://dstack.ai/docs/usage/dev-environments),
run [apps](https://dstack.ai/docs/usage/apps), and many more.

## Run it

Go ahead and run it:

```shell
dstack run train-mnist

RUN        WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
penguin-1  train-mnist  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: False, used: False

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
```

The `dstack run` command runs the workflow using the settings specified for the project configured with the
Hub application.

## Create a Hub project

As mentioned above, the default project runs workflows locally.
However, you can log into the application and create other projects that allow you to run workflows in the cloud.

<img src="https://dstack.ai/assets/dstack-hub-create-project.png" width="800px" />

If you want the project to use the cloud, you'll need to provide cloud credentials and specify settings such as the
artifact storage bucket and the region where the workflows will run.

<img src="https://dstack.ai/assets/dstack-hub-view-project.png" width="800px" />

Once a project is created, copy the CLI command from the project settings and execute it in your terminal.

<div class="termy">

```shell
dstack config --url http://127.0.0.1:3000 \
  --project gcp \
  --token b934d226-e24a-4eab-a284-eb92b353b10f
```

</div>

The `dstack config` command configures `dstack` to run workflows using the settings from
the corresponding project.

You can configure multiple projects and use them interchangeably (by passing the `--project` argument to the `dstack 
run` command. Any project can be set as the default by passing `--default` to the `dstack config` command.

Configuring multiple projects can be convenient if you want to run workflows both locally and in the cloud or if 
you would like to use multiple clouds.


## Manage resources

Consider that you have configured a project that allows you to use a GPU (e.g., a local backend if you have a GPU
locally, or an AWS or GCP backend).

Let's update our workflow and add `resources`.

```yaml
workflows:
  - name: train-mnist
    provider: bash
    commands:
      - pip install torchvision pytorch-lightning tensorboard
      - python examples/mnist/train_mnist.py
    artifacts:
      - path: ./lightning_logs
    resources:
      gpu:
        name: V100
        count: 1
```

Let's run the workflow:

```shell
dstack run train-mnist --project gcp

RUN        WORKFLOW     SUBMITTED  STATUS     TAG  BACKENDS
penguin-1  train-mnist  now        Submitted       local

Provisioning... It may take up to a minute. ✓

To interrupt, press Ctrl+C.

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
```

If your project is configured to use the cloud, the Hub application will automatically create the necessary cloud
resources to execute the workflow and tear them down once it is finished.

## More information

For additional information and examples, see the following links:

* [Quick start](https://dstack.ai/docs/quick-start)
* [Docs](https://dstack.ai/docs)
* [Tutorials](https://dstack.ai/tutorials/dolly)
* [Blog](https://dstack.ai/blog)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)