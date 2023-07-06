from dstack._internal.configurators import JobConfigurator
from dstack._internal.core.configuration import DevEnvironmentConfiguration


class DevEnvironmentConfigurator(JobConfigurator):
    conf: DevEnvironmentConfiguration
