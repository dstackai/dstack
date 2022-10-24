# Use cases

`dstack` lets you run any scripts in your cloud account from the command line. 
You don't have to worry about provisioning compute resources, setting up the environment, or managing data.

`dstack` is easy to use with Python scripts, Git, and your IDE.

## Processing data

If your script processes large data, you can specify the amount of memory to use
(via `.dstack/workflows.yaml`), and run it via `dstack run`. `dstack` will automatically
create a machine in your cloud account with required resources and run your script.

If your script produces data, you can mark those folders as artifacts
(via `.dstack/workflows.yaml`). `dstack` will automatically save them in your storage, 
so you can use them later (e.g. from other scripts).

If you want to reduce costs, you can explicitly tell `dstack` (via `.dstack/workflows.yaml`) to use spot instances.

## Training models

If your training script needs GPUs, you can specify their required number and type 
(via `.dstack/workflows.yaml`), and run it via `dstack run`. 
`dstack` will automatically
create a machine in your cloud account with required resources and run your script.

If your script produces data (e.g. checkpoints), you can mark the corresponding output 
folders as artifacts (via `.dstack/workflows.yaml`). `dstack` will automatically save them in your storage, 
so you can use them later (e.g. from other scripts).

If you want to reduce costs, you can explicitly tell `dstack` (via `.dstack/workflows.yaml`) to use spot instances.

## Dev environments

If you want to quickly create a dev environment such as VS Code or JupyterLab with required
resources (such as GPU or memory), you can specify the requirements (via `.dstack/workflows.yaml`) 
and run it via `dstack run`. `dstack` will automatically
create a machine in your cloud account with required resources and provide you a link to open the dev environment.
The dev environment will have your Git repo checked out and the required environment (Conda, CUDA, etc) configured.

## Running apps

If your script runs an application, you can tell `dstack` to expose the corresponding port (via `.dstack/workflows.yaml`), 
and run it via `dstack run`. `dstack` will automatically
create a machine in your cloud account with required resources and deploy your application.

## Managing data

If your script produces data, you can mark the corresponding output 
folders as artifacts (via `.dstack/workflows.yaml`). `dstack` will automatically save them in your storage, 
so you can use them later (e.g. from other scripts).

If you have local data, you can upload it to your storage (via `dstack tags add`) and refer to it 
from your scripts.

## Managing environments

When you run your script via `dstack run`, `dstack` automatically prepares the environment. This includes setting up 
the right version of CUDA, Conda, and Python.

If your script prepares Conda environment (that you'd like to reuse from other scripts), you can 
use `conda env create --prefix` to create it, and mark the corresponding folder as an artifact 
(via `.dstack/workflows.yaml`).

`dstack` will automatically save it in your storage, so you can use it later (e.g. from other scripts).

## When to use dstack?

`dstack` comes handy if you want to be able to quickly run scripts in the cloud while
keeping them highly reproducible.

`dstack` is an alternative to creating cloud machines manually
or to using the MLOps platforms (such as AWS SageMaker, KubeFlow, etc).

`dstack` is especially great if you prefer to use Git and your IDE.