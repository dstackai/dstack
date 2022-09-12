<div class="grid cards fit" markdown>
  - 
     <figure markdown> 

     ![](https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg){ width="300" align="center"}

      **Git-based CLI to run ML workflows on cloud**

      [![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge)](https://pypi.org/project/dstack/)
      [![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
      [![Slack](https://img.shields.io/badge/slack-chat-e01563?style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
    </figure>
</div>

# Intro

**dstack is an open-source CLI that allows to define ML workflows as code and run them on cloud. 
It provisions infrastructure and manages data automatically.**

To run ML workflows, often your local machine is not enough. 
That’s why it's necessary to automate the process of running ML workflows within the cloud infrastructure.

Instead of managing infrastructure yourself, writing own scripts, or using cumbersome MLOps platforms, with dstack, 
you can focus on code while dstack does management of dependencies, infrastructure, and data for you.

dstack is an alternative to KubeFlow, SageMaker, Docker, SSH, custom scripts, and other tools used often to
run ML workflows.

## Primary features

<div class="grid cards" markdown>

- **Environment setup** 

    No need to use Docker, configure CUDA yourself, etc. Just specify workflow 
    requirements in your code, and it will be pre-configured.

- **Data management** 

    Use tags to manage data and reuse it from workflows.
    Assign tags to finished workflows to reuse their artifacts from other workflows.

- **Dev environments** 

    Workflows may include tasks, applications, also dev environments, such as 
    IDEs and Jupyter notebooks.

- **Easy installation** 

    Just install the dstack CLI locally, and that's it.
    The CLI will use your local cloud credentials to run workflows. 
    The state is stored in an S3 bucket.

- **Git-focused** 

    When you run a workflow, dstack detects your local branch, commit hash, and local changes, 
    and uses it to run the workflow in the cloud.

- **Interruption-friendly** 

    Fully-leverage cloud spot/preemptive instances.
    If needed, store artifacts in real-time to resume workflows, e.g. if there were interrupted.

</div>

## Limitations and roadmap

!!! info "NOTE:"
    dstack is still under development.
    If you encounter bugs, please report them directly to [GitHub issues](https://github.com/dstackai/dstack/issues).
    For bugs, be sure to specify the detailed steps to reproduce the issue.

Below is the list of existing limitations:

- **Visual dashboard:** There's no visual dashboard to manage repos, runs, tags, and secrets. 
  It's already in work and is going to be released shortly (Q3, 2022).
- **Interactive logs:** Currently, output logs of workflows are not interactive. Means, you can't 
  use output to display progress (e.g. via `tqdm`, etc.) Until it's supported, it's recommended that 
  you report progress via TensorBoard event files or hosted experiment trackers (e.g. WanB, Comet, 
  Neptune, etc.) 
- **Git hosting providers:** Currently, dstack works only with the GitHub.com repositories. If you'd like to use
  dstack with other Git hosting providers (or without using Git at all), add or upvote the 
  corresponding issue.
- **Cloud providers:** dstack currently works only with AWS. If you'd like to use dstack with GCP, 
  Azure, or Kubernetes, add or upvote the corresponding issue.
- **Providers:** Advanced providers, e.g. for distributed training and data processing, are in plan.