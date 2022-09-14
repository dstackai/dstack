# Providers

Providers define how the workflow is executed and what properties can be specified for the workflow in the 
`.dstack/workflows.yaml` file.

Providers allow to run tasks, applications, and even dev environments, such as 
IDEs and Jupyter notebooks.

## Main provider

<div class="grid cards" markdown>
- **Bash** 

    Runs shell commands

    [:octicons-arrow-right-24: Reference](../providers/bash.md)

</div>

## Other providers

<div class="grid cards" markdown>

- **VS Code** 

    Launches a VS Code dev environment

    [:octicons-arrow-right-24: Reference](code.md)

- **JupyterLab** 

    Launches a JupyterLab dev environment

    [:octicons-arrow-right-24: Reference](lab.md)

- **Jupyter Notebook** 

    Launches a Jupyter notebook

    [:octicons-arrow-right-24: Reference](notebook.md)

[//]: # (- **Torchrun** )

[//]: # (    Runs a distributed training)

[//]: # (    [:octicons-arrow-right-24: Reference]&#40;torchrun.md&#41;)

- **Docker** 

    Runs a Docker image

    [:octicons-arrow-right-24: Reference](docker.md)

</div>