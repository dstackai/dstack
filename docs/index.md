# What is dstack?

`dstack` is a lightweight command-line tool for running reproducible ML workflows in the cloud.

## Features

 * Define workflows (incl. their dependencies, environment and hardware requirements) as code.
 * Run workflows in the cloud using the `dstack` CLI. dstack provisions infrastructure and environment for you in the cloud.
 * Save output artifacts of workflows and reuse them in other workflows.

## Getting started

 * Install `dstack` CLI locally (e.g. via pip)
 * Make sure the cloud account credentials are configured locally
 * Configue the `dstack` CLI with the cloud region name and a storage bucket name (to use to provision infrastructure and save data)
 * Define workflows as code (within your Git project directory)
 * Use the `dstack` CLI to run workflows, manage their state and artifacts

## How does it work?

 * You define workflows in `.dstack/workflows.yaml` within your project: environment and hardware requirements, dependencies, artifacts, etc.
 * You use the `dstack run` CLI command to run workflows
 * When you run a workflow, the CLI provisions infrastructure, prepares environment, fetches your code,
   downloads dependencies, runs the workflow, saves artifacts, and tears down infrastructure.
 * You assign tags to finished run, e.g. to reuse their output artifacts in other workflows.
 * Use workflows to process data, train models, host apps, and launch dev environments. 

[//]: # (## Roadmap)

[//]: # ()
[//]: # (dstack is available as a beta.)

[//]: # (If you encounter bugs, please report them directly to [GitHub issues]&#40;https://github.com/dstackai/dstack/issues&#41;.)

[//]: # (For bugs, be sure to specify the detailed steps to reproduce the issue.)

[//]: # ()
[//]: # (Below is the list of existing limitations:)

[//]: # ()
[//]: # (- **Visual dashboard:** There's no visual dashboard to manage repos, runs, tags, and secrets. )

[//]: # (  It's already in work and is going to be released shortly &#40;Q3, 2022&#41;.)

[//]: # (- **Interactive logs:** Currently, output logs of workflows are not interactive. Means, you can't )

[//]: # (  use output to display progress &#40;e.g. via `tqdm`, etc.&#41; Until it's supported, it's recommended that )

[//]: # (  you report progress via TensorBoard event files or hosted experiment trackers &#40;e.g. WanB, Comet, )

[//]: # (  Neptune, etc.&#41; )

[//]: # (- **Git hosting providers:** Currently, dstack works only with the GitHub.com repositories. If you'd like to use)

[//]: # (  dstack with other Git hosting providers &#40;or without using Git at all&#41;, add or upvote the )

[//]: # (  corresponding issue.)

[//]: # (- **Cloud providers:** dstack currently works only with AWS. If you'd like to use dstack with GCP, )

[//]: # (  Azure, or Kubernetes, add or upvote the corresponding issue.)

[//]: # (- **Providers:** Advanced providers, e.g. for distributed training and data processing, are in plan.)