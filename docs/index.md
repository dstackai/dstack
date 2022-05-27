# What is dstack?

##### Automate continuous training workflows and version training data

🚀 With dstack, you don't need sophisticated MLOps platforms anymore – just as you don't need to manually manage your 
 infrastructure or version your data yourself.

!!! info ""
    dstack allows you to run training from your IDE without having to commit local changes to Git before every run. 
    At the same time, dstack tracks uncommitted changes and also saves output artifacts of your workflows automatically.
    
    Using dstack is very easy. All you need to do is link your cloud account to dstack, and add declarative configuration 
    files to your project. Then you can run any workflow from the CLI, and dstack will take care of the rest.

#### Why use dstack?

- **Infrastructure**: No more pain with setting up infrastructure. Define what infrastructure you need in your configuration files,
  and dstack will automatically set up the required infrastructure in your cloud and will tear it down once it's not needed.
- **Reproducibility**: Every workflow is fully reproducibly
- **Data versioning**: All output artifacts are tracked automatically in real-time as your workflows is running.
  You can assign a tag to any run, and reuse its artifacts from other workflows.

#### More reasons to use dstack:

- **Python scripts**: dstack makes it very easy to run trainings with Python scripts.
- **Git**: Fully integrated with Git. To run a workflow, you don't have to commit local changes. dstack tracks it automatically.
- **Interruptible workflows**: dstack helps you use interruptible (cheaper) instances for long trainings as it may save checkpoints in real-time
  and resume from where it finished.
- **Easy to use**: No changes in your code is required. Just add configuration files and run workflows via the CLI.
- **Interoperability**: A variety of built-in providers that support various use-cases, as well as an API to extend the platform if needed.

**Here's what you can do with dstack:**

- **Infrastructure as code**: Forget about infrastructure. Just define your workflows and the resources they need declaratively and run your workflows
  interactively via the CLI.
- **Use existing cloud**: Use your existing cloud account to provision infrastructure. You only need to provide dstack credentials to 
  create EC2 instances.
- **Version and reuse data**: Version and reuse data. The output artifacts are saved automatically. Put a tag to a particular run, and reuse its 
  artifacts from other workflows.
- **Track experiments**: Use a experiment tracker of your choice to track metrics, incl. W&B, Comet, Neptune, etc.
- **Automate workflows**: Automate preparing data, training, validating, and deployment of your models.