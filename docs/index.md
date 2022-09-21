# What is dstack?

`dstack` is a lightweight command-line tool for running reproducible ML workflows in the cloud.

## Features

 * Define workflows, incl. dependencies, environment, and required compute resources, via declarative configuration files
 * Run workflows in the cloud via the `dstack` CLI.
 * Save output artifacts of workflows and reuse them in other workflows.
 * Use workflows to process data, train models, host apps, and launch dev environments.

## How does it work?

 * Install `dstack` CLI locally
 * Make sure the AWS account credentials are configured locally
 * Configure the AWS region (where to provision infrastructure) and an S3 storage bucket name (where to save data)
 * Define define workflows in `.dstack/workflows.yaml` within your project directory
 * Use the `dstack` CLI to run workflows, manage their state and artifacts 
 * When you run a workflow, the `dstack` CLI  provisions the required cloud resources, 
   fetches your code, prepares environment, downloads dependencies, runs the workflow,
   saves artifacts, and tears down cloud resources.



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