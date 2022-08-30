# Introduction to dstack

To run ML workflows, your local machine is often not enough, so you need a way 
to automate running these workflows using the cloud infrastructure.

Instead of managing infrastructure yourself, writing custom scripts, or using cumbersome MLOps platforms, 
define your workflows in code and run from command-line.

dstack is an alternative to SSH, custom scripts, Docker, KubeFlow, SageMaker, and other tools used 
for running ML workflows.

### Primary features of dstack:

1. **Infrastructure as code:** Define workflows and infrastructure requirements declaratively as code.
   dstack sets up and tears down infrastructure automatically.
2. **GitOps approach:** dstack is integrated with Git and tracks code automatically.
   No need to push local changes before running a workflow.
3. **Artifacts and tags:** Artifacts are the first-class citizens.
   Once the workflow is finished, assign a tag to it and reuse artifacts in other workflows.
4. **Environment setup:** No need to build own Docker images or setup CUDA yourself. Just specify Conda 
   requirements and they will be pre-configured.
5. **Interrupted workflows:** Artifacts can be stored in real-time, so you can fully-leverage spot/preemptive instances.
   Resume workflows from where they were interrupted.
6. **Technology-agnostic:** No need to use specific APIs in your code. Anything that works locally, can run via dstack.
7. **Dev environments:** Workflows may be not only tasks or applications but also dev environments, such as VS Code, JupyterLab, and Jupyter notebooks.
8. **Very easy setup:** Just install the dstack CLI and run workflows
   in your cloud using your local credentials. The state is stored in your cloud storage. 
   No need to set up any complicated software.
