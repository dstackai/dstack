# Use cases

`dstack` is a lightweight command-line utility that lets you run ML workflows in the cloud,
while keeping them highly reproducible.

## Provisioning infrastructure

If your script (that processes data, trains a model, or runs a web application) needs resources that you 
don't have locally (e.g. more GPU), or if you want to run multiple scripts in parallel, you can specify 
required resources via `.dstack/workflows.yaml`, and then run your scripts via `dstack run`.

`dstack` will automatically create machines in the configured cloud account with required resources, 
and run your scripts.

## Utilizing spot instances 

If you want to reduce costs, you can explicitly tell `dstack` (via `.dstack/workflows.yaml`) to use 
interruptible instances (also known as spot instances).

## Managing environment

When you run scripts via `dstack run`, `dstack` automatically prepares the environment. This includes setting up 
the right version of CUDA, Conda, and Python.

If your script prepares Conda environment (that you'd like to reuse from other scripts), you can 
use `conda env create --prefix` to create it, and mark the corresponding folder as an artifact 
(via `.dstack/workflows.yaml`) so you can use it later (e.g. from other scripts).

## Managing & versioning data

If your script produces data, you can mark the corresponding output 
folders as artifacts (via `.dstack/workflows.yaml`). `dstack` will automatically save them in your storage, 
so you can use them later (e.g. from other scripts).

## Creating dev environments

If you want to quickly create a dev environment such as VS Code or JupyterLab with required
resources (such as GPU or memory), you can specify the requirements (via `.dstack/workflows.yaml`) 
and run it via `dstack run`. `dstack` will automatically
create a machine in your cloud account with required resources and provide you a link to open the dev environment.
The dev environment will have your Git repo checked out and the required environment (Conda, CUDA, etc) configured.

## Driving best practices

`dstack` is as lightweight utility that can be used together with Git, Python scripts, and your IDE.
It's designed to drive simplicity and the best engineering practices (such as versioning code, writing modular code,
using tests, versioning artifacts, keeping your code independent of proprietary APIs, not depending on Kubernetes, etc).

Consider `dstack` as a more simple alternative to AWS SageMaker, GCP Vertex AI, KubeFlow, AirFlow, Argo, and
other complex MLOps solutions.
