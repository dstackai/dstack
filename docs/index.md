# Introduction to dstack

To run ML workflows, your local machine is often not enough. 
That’s why you often have to automate running ML workflows withing the cloud infrastructure.

Instead of managing infrastructure yourself, writing own scripts, or using cumbersome MLOps platforms, with dstack, 
you can focus on code while dstack does management of dependencies, infrastructure, and data for you.

dstack is an alternative to KubeFlow, SageMaker, Docker, SSH, custom scripts, and other tools used often to
run ML workflows.

### Primary features of dstack:

1. **Git-focused:** Define workflows and their hardware requirements declaratively in your code.
   When you run a workflow, dstack detects the current branch, commit hash, and local changes.
2. **Data management:** Workflow artifacts are the 1st-class citizens.
   Assign tags to finished workflows to reuse their artifacts from other workflows. 
   Version data using tags.
3. **Environment setup:** No need to build custom Docker images or setup CUDA yourself. Just specify Conda 
   requirements and they will be pre-configured.
4. **Interruption-friendly:** Because artifacts can be stored in real-time, you can leverage interruptible 
   (spot/preemptive) instances. Workflows can be resumed from where they were interrupted.
5. **Technology-agnostic:** No need to use specific APIs in your code. Anything that works locally, can run via dstack.
6. **Dev environments:** Workflows may be not only tasks and applications but also dev environments, incl. 
   IDEs and notebooks.
7. **Very easy setup:** Install the dstack CLI and run workflows
   in the cloud using your local credentials. The state is stored in an S3 bucket. 
   No need to set up anything else.
