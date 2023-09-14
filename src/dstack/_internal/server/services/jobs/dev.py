from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.server.services.jobs.base import JobConfigurator


class DevEnvironmentJobConfigurator(JobConfigurator):
    TYPE: ConfigurationType = ConfigurationType.DEV_ENVIRONMENT
