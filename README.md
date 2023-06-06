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

`dstack` makes it very easy for ML engineers to run development environments and ML tasks on any cloud.

Development environments and tasks can be defined via simple YAML configurations and quickly run with a single command
on any configured cloud, whether it's AWS, GCP, or Azure.

The tool is open-source and can be self-hosted. You can run it on your local machine or deploy it to your own cloud. The
tool will orchestrate development environments and tasks for your entire ML team.

**`dstack` makes it very easy to:**

- Configure and reuse prebuilt environments (without Docker)
- Utilize spot instances
- Save and reuse output artifacts
- Use multiple clouds via the same simple interface

More importantly, `dstack` increases your productivity as an ML engineer, allowing you to focus on ML without worrying
  about infrastructure, costs, etc.

**🍒 is, `dstack` is 100% open-source and can be self-hosted**

## Installation and setup

To use `dstack`, install it with `pip` and start the Hub application.

```shell
pip install "dstack[aws,gcp,azure]"
dstack start
```

The server will set up a default project to run dev environments and tasks locally. 
To run dev environments and tasks in the cloud, log into the UI, create the corresponding project,
and [configure](https://dstack.ai/docs/guides/projects) the CLI to use it.

## Configurations

A configuration is a YAML file that describes what you want to run.

> **Note:**
> All configuration files must be named with the suffix `.dstack.yml`. For example,
> you can name the configuration file `.dstack.yml` or `app.dstack.yml`. You can define
> these configurations anywhere within your project.

Configurations can be of two types: `dev-environment` and `task`.

Below is a configuration that runs a dev environment with a pre-built environment to which you can connect via VS Code Desktop.

```yaml
type: dev-environment
setup:
  - pip install -r requirements.txt
ide: vscode
```

Here's an example of a task configuration.
A task can be either a batch job, such as training or fine-tuning a model, or a web application.

```yaml
type: task
setup:
  - pip install -r requirements.txt
ports:
  - 7860
commands:
  - gradio app.py
```

## CLI

To run a configuration, use the [`dstack run`](https://dstack.ai/docs/reference/cli/run.md) command and pass the path to the 
directory with the configuration.

```shell
$ dstack run . 

 RUN          WORKFLOW  SUBMITTED  USER   STATUS     INSTANCE 
 fast-moth-1  ssh       now        admin  Submitted  a2-highgpu-1g        

Starting SSH tunnel...

To open in VS Code Desktop, use one of these links:
  vscode://vscode-remote/ssh-remote+fast-moth-1/workflow
  vscode-insiders://vscode-remote/ssh-remote+fast-moth-1/workflow

To exit, press Ctrl+C.
```

The CLI automatically provisions the required cloud resources and forwards the ports to your local machine.
If you interrupt the run, the cloud resources will be released automatically.

## Profiles

The `.dstack/profiles.yml` file allows to describe multiple profiles. 
ach profile can configure the project to use and the resources required for the run.

```yaml
profiles:
  - name: gpu-large
    project: gcp
    resources:
       memory: 48GB
       gpu:
         memory: 24GB
    default: true
```

If you have configured the default profile, the `dstack run` command will use it automatically.
Otherwise, you can always specify the profile using `--profile PROFILE`.

## More information

For additional information and examples, see the following links:

* [Docs](https://dstack.ai/docs)
* [Examples](https://github.com/dstackai/dstack-examples/blob/main/README.md)
* [Blog](https://dstack.ai/blog)
* [Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
 
##  Licence

[Mozilla Public License 2.0](LICENSE.md)