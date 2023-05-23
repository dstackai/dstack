---
date: 2023-05-23
description:  Learn how to elevate your ML workflow with using dev environments over manual SSH.
slug: embrace-dev-environments
---

# Embrace Dev Environments, Leave Manual SSH Behind

__Overcoming the limitations of dev environments for ML projects.__

SSH is frequently an indispensable tool for ML engineers. In this discussion, we will delve into the drawbacks of using 
SSH manually and the advantages of embracing dev environments, which can significantly enhance your productivity as an ML
engineer.

<!-- more -->

## Why SSH is the frequently used for ML

If we are working with a cloud instance (which is often the case in ML projects, especially in the enterprise setting),
we often end up using SSH as the main developer interface to access the instance.

<div class="termy">

```shell
$ ssh username@remotehost

root@79fb138f2996:/# 
```

</div>

Why? It's easy to use with any cloud. It's secure. It allows forwarding ports to your local machine. It allows you to
use the developer tools of your choice. You can either use it via the command line, attach your code editor to it, or
use it via a Jupyter notebook running on the instance.

Finally, and even more importantly, SSH gives you direct access to the environment, allowing you to debug your code and
have the shortest feedback loop possible.

## Drawbacks of using SSH for cloud

While SSH makes remote access easier, it by no means helps you set up the environment or provision cloud resources.

In traditional development, you can create a cloud instance, do the setup once, and use the instance for a long period
of time. In ML, you can't spin up an expensive cloud instance for a long period of time. That's why if you want to use
SSH, you have to set up the environment and manage the cloud instance yourself.

Ideally, you'd like to define your environment and instance requirements as code and be able to spin them up on demand
while keeping all the advantages of SSH.

## Limitations of dev environments

The concept of dev environments aims to solve this issue. It allows you to define your dev environment configuration as
code and then launch it on demand. But if it sounds so good, why isn't it frequently used for ML?

Here are some of the reasons that come to mind:

* Most dev environments are managed services and can't compare in terms of flexibility to SSH, which is open-source and
  works with any cloud vendor.
* ML has a lot of specifics: you may want to use a particular cloud account (e.g., where your data or compute reside),
  spot instances, or other ML-specific infrastructure, etc.

While dev environments are growing in popularity, there is still a gap before they become the new standard for ML. At
dstack, we aim to change this

## How dstack is solving this

`dstack` is an [open-source](https://github.com/dstackai/dstack) tool licensed under the Mozilla Public License 2.0 and
works with any cloud vendor. Secondly, `dstack` focuses entirely on ML challenges. So, how does it work?

<div class="termy">

```shell
$ pip install "dstack[aws,gcp,azure]"
dstack start
```

</div>

The `dstack start` command runs a lightweight server that manages cloud credentials and orchestrates runs.

!!! info "NOTE:"
    By default, it runs dev environments locally.
    To run dev environments in the cloud, all you need to do is to configure the corresponding project by providing the 
    cloud credentials.

Dev environments can be defined via YAML (under the `.dstack/workflows` folder).

<div editor-title=".dstack/workflows/code-gpu.py">

```yaml
workflows:
  - name: code-gpu
    provider: code
    python: 3.11
    setup:
      - pip install -r dev-environments/requirements.txt
    resources:
      gpu:
        count: 1
    cache:
       - path: ~/.cache/pip
       - path: ./models
```

</div>

Once defined, you can run them via the `dstack run` command:

<div class="termy">

```shell
$ dstack run code-gpu

RUN      WORKFLOW  SUBMITTED  STATUS     TAG
shady-1  code-gpu  now        Submitted  
 
Starting SSH tunnel...

To exit, press Ctrl+C.

Web UI available at http://127.0.0.1:51845/?tkn=4d9cc05958094ed2996b6832f899fda1
```

</div>

For convenience, `dstack` uses an exact copy of the source code that is locally present in the folder where you use the `dstack` command.

If you click the URL, it will open the web-based VS Code IDE.

![](../../assets/images/dstack-dev-environments-code.png){ width=800 }

`dstack` automatically and securely forwards the ports of the dev environment to your local machine
so onlu you can access it.

You can use dev environments to explore data, train models, run apps, and do other ML tasks
without wasting any time on managing infrastructure or setting up the environment.

On top of that, you get a lot of other features which you can read about in the [documentation](../../docs/index.md).

!!! info "NOTE:"
    Interested? Give it a try and let us know what you think!
    
    [Discuss on Slack](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ){ .md-button .md-button--primary }