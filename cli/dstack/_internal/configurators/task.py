from dstack._internal.configurators import JobConfigurator
from dstack._internal.core.configuration import TaskConfiguration


class TaskConfigurator(JobConfigurator):
    conf: TaskConfiguration
