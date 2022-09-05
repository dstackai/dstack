<div class="grid cards fit" markdown>
  - 
     <figure markdown> 

     ![](https://raw.githubusercontent.com/dstackai/dstack/master/docs/assets/logo.svg){ width="300" align="center"}

      **Git-based CLI to run ML workflows on cloud**

      [![PyPI](https://img.shields.io/pypi/v/dstack?style=for-the-badge&color=brightgreen)](https://pypi.org/project/dstack/)
      [![PyPI - License](https://img.shields.io/pypi/l/dstack?style=for-the-badge&color=blue)](https://github.com/dstackai/dstack/blob/master/LICENSE.md)
      [![Slack](https://img.shields.io/badge/slack-chat-e01563?style=for-the-badge)](https://join.slack.com/t/dstackai/shared_invite/zt-xdnsytie-D4qU9BvJP8vkbkHXdi6clQ)
    </figure>
</div>

# Intro

To run ML workflows, often your local machine is not enough. 
That’s why it's necessary to automate the process of running ML workflows within the cloud infrastructure.

Instead of managing infrastructure yourself, writing own scripts, or using cumbersome MLOps platforms, with dstack, 
you can focus on code while dstack does management of dependencies, infrastructure, and data for you.

dstack is an alternative to KubeFlow, SageMaker, Docker, SSH, custom scripts, and other tools used often to
run ML workflows.

## Primary features

<div class="grid cards" markdown>

- **Git-focused** 

    Define workflows and their hardware requirements as code. 
    When you run a workflow, dstack detects the current branch, commit hash, and local changes.

- **Data management** 

    Workflow artifacts are the 1st-class citizens.
    Assign tags to finished workflows to reuse their artifacts from other workflows. 
    Version data using tags.

- **Environment setup** 

    No need to build custom Docker images or setup CUDA yourself. Just specify Conda 
    requirements and they will be pre-configured.

- **Interruption-friendly** 

    Because artifacts can be stored in real-time, you can leverage interruptible 
    (spot/preemptive) instances.

- **Dev environments** 

    Workflows may be not only tasks and applications but also dev environments, such as 
    IDEs and Jupyter notebooks.

- **Very easy setup** 

    Install the dstack CLI and run workflows
    in the cloud using your local credentials. The state is stored in an S3 bucket.

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