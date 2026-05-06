---
name: dstack-dev
description: |
  dstack is an open-source control plane for GPU provisioning and orchestration across GPU clouds, Kubernetes, and on-prem clusters.

  This skill is specifically designed for using dstack's dev environments when it's required to experiment with code, tune and debug workloads before running them as tasks or services. It covers best practices for configuring dev environments, connecting to them via SSH to run commands interactively, e.g. to experiment and debug code.
  
  For example, this skill is ideal to test various configurations and find optimal commands and parameters to use with a specific framework on specific hardware.
---

# Using dev environments for experimenting, tuning, and debugging code

## Workflow

Below is a brief playbook for using dev environments when you need to tune and debug your code before running it on a specific hardware as a task or service.

1. **`dstack` skill**: Use the `dstack` skill that covers core capabilities of `dstack` for managing fleets, tasks, and services. This includes best practices for applying configurations, monitoring workloads, and troubleshooting common issues.
2. **Fleet**: Select an instance configuration that matches the hardware requirements you need to run the workload. This primarily includes the number of GPUs, the GPU name, and the minimum size of the disk (e.g. enough to store model weights). You can use `dstack offer` CLI command to see all available offers across the backends configured for the project. Once you know which instance configuration you want to use, ensure there is a matching fleet. Create a fleet if needed. `dstack` supports two types of backends: VM-based and container-based. The primary difference is that VM-based backends allow pre-provisioned instances (allowing you to set `nodes` to <number> greater than `0`); this allows re-using instances across runs. Container backends provision instances on-demand (requiring you to set `nodes` to a range, e.g. `0..<number>`) and delete them once the run is complete. SSH fleets work similarly to VM-based fleets, but they allow you to run workloads on on-prem instances. When it's possible, it's recommended to use VM-based fleets since you can pre-provision instances and re-use them across runs. This is especially useful if you want to try different Docker images. But the final choice depends on your use case and requirements.
3. **Docker image**: Select a Docker image that is most recommended for your workload (including the GPU model, the framework, etc.). The Docker image must match what you later plan to use with tasks or services once you finish development. If the workload downloads models, kernels, or framework artifacts, consider mounting an optional instance volume at `/root/.cache`. In some special cases, when it's critically important to test multiple Docker images from the same run, with VM-based fleets, it's possible to set `docker: true` on a run configuration instead of setting `image`. This allows you to use `docker run` directly inside your run and try multiple images without needing to re-submit your run. The downside of it is manual invocation of `docker run` and the need to use a VM-based backend or SSH fleet that may not always be available.
4. **Dev environment**: Once there is a matching fleet, and you decided on the Docker image (or to use `docker run`), create a dev environment configuration, and specify a fleet that you intend to use. Invoke `dstack apply` CLI command on this configuration. Follow the `dstack` skill guidance on how to apply configuration and troubleshoot common issues. For example, it's recommended to run it in the detached mode (by passing `-d`).
5. **SSH**: After the run status changes to `running`, use `dstack attach <run name> --logs` CLI command to configure SSH access inside the run. Once the command is successful, you can use `ssh <run name>` to connect inside the dev environment, and invoke commands. Run commands to experiment with your code, tune parameters, and debug issues. Once you confirm that commands are fully tested and tuned, you can use the same commands for a task or service configuration. **IMPORTANT**: both `dstack attach` and `ssh` commands require full-access and must run outside of the sandbox. If you run them inside the sandbox, they will fail.
6. **Iterate**: If you are not using `docker: true`, to try another Docker image, you can stop the run, change the image in the dev environment configuration, and run it again. The same applies to a fleet configuration. If you decide to try different hardware, you can consider creating another fleet or updating the existing one (would require instances to stop first if it's a container-based fleet).

## Example: inference

To summarize, below is the recommended workflow for using dev environments for tuning and debugging code:

Just as an example, let's say you want to find the right hardware and parameters to deploy a model using a specific framework and ensure it works.

1. Make sure you get a good understanding of what framework you plan to use, what GPUs and what disk space will be required given the model and its variant you want to deploy. Check the framework or model's official docs, cookbook, or model card for the initial baseline.
2. Use `dstack offer` to find the right instance configuration that matches your requirements. Ensure there is a matching fleet, and create one if needed.
3. Select a Docker image that is most recommended for your use case. If the workload downloads models, kernels, or framework artifacts, consider an optional `/root/.cache` instance volume. If you want to try multiple images, consider using `docker: true` option (requires a VM-based backend).
4. Create a dev environment configuration, and apply it.
5. Once the run is `running`, use `dstack attach` to configure SSH access.
6. Use `ssh` to connect to the dev environment and run commands to experiment, tune, and debug your code.
7. Once you are happy with the results, use the same hardware and commands to create a task or service configuration and run it.
8. If you want to try different hardware or Docker images, iterate by updating the fleet or dev environment configuration and re-applying it.
9. Make sure to run `dstack attach` and `ssh` commands outside of the sandbox, otherwise they will fail.
10. Enable `dstack` skill before using the above workflow.
