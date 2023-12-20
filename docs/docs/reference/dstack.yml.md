# .dstack.yml

With `dstack`, you can define what you want to run as YAML configuration files 
and run them using the `dstack run` command. 

!!! info "Filename"
    Configuration files must have a name ending with `.dstack.yml` (e.g., `.dstack.yml` or `dev.dstack.yml` are both acceptable).
    Configuration files can be placed either in the project's root directory or in any nested folder. 

Configurations can be of three types: `dev-environment`, `task`, and `service`.

Below, you'll find the complete reference detailing all available properties for each type of configuration.

## dev-environment

This configuration type allows you to provision a [dev environment](../guides/dev-environments.md) with the required cloud resources, 
code, and environment.

#SCHEMA# dstack._internal.core.models.configurations.DevEnvironmentConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## task

This configuration type allows you to run [tasks](../guides/tasks.md) like training scripts, batch jobs, or web apps.

#SCHEMA# dstack._internal.core.models.configurations.TaskConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true

## service

This configuration type allows you to deploy models or web apps as [services](../guides/services.md).

#SCHEMA# dstack._internal.core.models.configurations.ServiceConfiguration
    overrides:
      show_root_heading: false
      type:
        required: true
