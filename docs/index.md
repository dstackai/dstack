# What is dstack?

`dstack` is a lightweight and open-source command-line tool to provision infrastructure for ML workflows.

## Features

 * Define your ML workflows declaratively, incl. their dependencies, environment, and required compute resources 
 * Run workflows via the `dstack` CLI. Have infrastructure provisioned automatically in a configured cloud account. 
 * Save output artifacts, such as data and models, and reuse them in other ML workflows
 * Use `dstack` to process data, train models, host apps, and launch dev environments

## How does it work?

 * Install `dstack` locally (a simple `pip install` will do)
 * Configure the cloud credentials locally (e.g. via `~/.aws/credentials`)
 * Run `dstack config` to configure the cloud region (to provision infrastructure) and the S3 bucket (to store data)
 * Define ML workflows in `.dstack/workflows.yaml` (within your existing Git repository)
 * Run ML workflows via the `dstack run` CLI command. Use other CLI commands to show status, manage state, artifacts, etc. 

!!! tip "NOTE:"
    When you run an ML workflow via the `dstack` CLI, it provisions the required compute resources (in a configured cloud
    account), sets up environment (such as Python, Conda, CUDA, etc), fetches your code, downloads deps,
    saves artifacts, and tears down compute resources.