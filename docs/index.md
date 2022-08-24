# Introduction to dstack

To run ML workflows, your local machine is often not enough, so you need a way 
to automate running these workflows using the cloud infrastructure.

Instead of configuring cloud instances manually, writing custom scripts, or even using complicated MLOps platforms, 
now you can run workflows with a single dstack command.

dstack is an alternative to SSH, custom scripts, Docker, KubeFlow, SageMaker, and other tools used 
for running ML workflows.

### Primary features of dstack:

1. **Declarative workflows:** You define workflows within `./dstack/workflows.yaml` file 
  and run them via the CLI.
2. **Agnostic to tools and APIs:** No need to use specific APIs in your code. Anything that works locally, can run via dstack.
3. **Artifacts are the first-class citizens:** As you're running a workflow, artifacts are stored in real-time.
  If interrupted, resume from where it's stopped.
  Once the workflow is finished, assign a tag to it and reuse artifacts in other workflows.
4. **GitOps approach:** dstack is fully integrated with Git. Run workflows from the CLI. dstack tracks code automatically.
  No need to push your changes before running a workflow.
5. **Very easy setup:** No need to set up any complicated software. Just install the dstack CLI and run workflows
  in your cloud using your local credentials. The state is stored in your cloud storage. Work alone or collaborate within a team.
