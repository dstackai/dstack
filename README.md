<div align="center">
<h1 align="center">
  <a target="_blank" href="https://dstack.ai">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo-dark.svg"/>
      <img alt="dstack" src="https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/images/dstack-logo.svg" width="350px"/>
    </picture>
  </a>
</h1>

<h3 align="center">
Develop ML faster. Use any cloud.
</h3>

<p align="center">
<a href="https://dstack.ai/docs" target="_blank"><b>Docs</b></a> • 
<a href="https://dstack.ai/examples/dolly" target="_blank"><b>Examples</b></a> •
<a href="https://dstack.ai/blog" target="_blank"><b>Blog</b></a> •
<a href="https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ" target="_blank"><b>Slack</b></a>
</p>

[![Last commit](https://img.shields.io/github/last-commit/dstackai/dstack?style=flat-square)](https://github.com/dstackai/dstack/commits/)
[![PyPI - License](https://img.shields.io/pypi/l/dstack?style=flat-square&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
</div>

`dstack` makes it very easy for ML engineers to run dev environments, pipelines and apps cost-effectively 
on any cloud.

## Installation and setup

To use `dstack`, install it with `pip` and start the Hub application.

```shell
pip install "dstack[aws,gcp,azure]"
dstack start
```

The `dstack start` command starts the Hub server, and creates the default project to run everything locally.

To enable Hub to run dev environments, pipelines, and apps in your preferred cloud account (AWS, GCP, Azure, etc), 
log in to Hub, and configure the corresponding project.

## Running a dev environment

A dev environment is a virtual machine that includes the environment and an interactive IDE or notebook setup
based on a pre-defined configuration.

Go ahead and define this configuration via YAML (under the `.dstack/workflows` folder).

```yaml
workflows:
  - name: code-gpu
    provider: code
    setup:
      - pip install -r dev-environments/requirements.txt
    resources:
      gpu:
        count: 1
```

The YAML file allows you to configure hardware resources, 
set up the Python environment, expose ports, configure cache, and many more.

Now, you can start it using the `dstack run` command:

```shell
$ dstack run code-gpu

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  code-gpu  now        Submitted  
 
Starting SSH tunnel...

To exit, press Ctrl+C.

Web UI available at http://127.0.0.1:10000/?tkn=4d9cc05958094ed2996b6832f899fda1
```

If you configure a project to run dev environments in the cloud, `dstack` will automatically provision the
required cloud resources, and forward ports of the dev environment to your local machine. 

When you stop the dev environment, `dstack` will automatically clean up cloud resources.

## Running a pipeline

A pipeline is a set of pre-defined configurations that allow to process data, train or fine-tune models, do batch inference 
or other tasks.

Go ahead and define such a configuration via YAML (under the `.dstack/workflows` folder).

```yaml
workflows:
  - name: train-mnist-gpu
    provider: bash
    commands:
      - pip install -r pipelines/requirements.txt
      - python pipelines/train.py
    artifacts:
      - ./lightning_logs
    resources:
      gpu:
        count: 1
```

The YAML file allows you to configure hardware resources and output artifacts, set up the
Python environment, expose ports, configure cache, and many more.

Now, you can run the pipeline using the `dstack run` command:

```shell
$ dstack run train-mnist-gpu

RUN      WORKFLOW         SUBMITTED  STATUS     TAG
shady-1  train-mnist-gpu  now        Submitted  
 
Provisioning... It may take up to a minute. ✓

GPU available: True, used: True

Epoch 1: [00:03<00:00, 280.17it/s, loss=1.35, v_num=0]
```

If you configure a project to run pipelines in the cloud, the `dstack run` command will automatically provision the 
required cloud resources.

After the pipeline is stopped or finished, `dstack` will save output artifacts and clean up cloud resources.

## Running an app

An app can be either a web application (such as Streamlit, Gradio, etc.) or an API endpoint (like FastAPI, Flask, etc.)
setup based on a pre-defined configuration.

Go ahead and define this configuration via YAML (under the `.dstack/workflows` folder).

```yaml
workflows:
  - name: fastapi-gpu
    provider: bash
    ports:
      - 3000
    commands:
      - pip install -r apps/requirements.txt
      - uvicorn apps.main:app --port 3000 --host 0.0.0.0
    resources:
      gpu:
        count: 1
```

The configuration allows you to customize hardware resources, set up the Python environment, 
configure cache, and more.

Now, you can run the app using the `dstack run` command:

```shell
$ dstack run fastapi-gpu
 RUN           WORKFLOW     SUBMITTED  STATUS     TAG
 silly-dodo-1  fastapi-gpu  now        Submitted     

Starting SSH tunnel...

To interrupt, press Ctrl+C.

INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:3000 (Press CTRL+C to quit)
```

If you configure a project to run apps in the cloud, `dstack` will automatically provision the required cloud
resources, and forward ports of the app to your local machine.
If you stop the app, it will automatically clean up cloud resources.

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](https://github.com/dstackai/dstack-examples/blob/main/README.md)
* [Blog](https://dstack.ai/blog)
* [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)