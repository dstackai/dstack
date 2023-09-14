from typing import List

from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.core.models.runs import Job, JobSpec, RunSpec
from dstack._internal.server.services.jobs.base import JobConfigurator
from dstack._internal.server.services.jobs.dev import DevEnvironmentJobConfigurator


def get_jobs_from_run_spec(run_spec: RunSpec) -> List[Job]:
    job_specs = _get_job_specs(run_spec)
    return [Job(job_spec=s, job_submissions=[]) for s in job_specs]


def _get_job_specs(run_spec: RunSpec) -> List[JobSpec]:
    job_configurator = _get_job_configurator(ConfigurationType(run_spec.configuration.type))
    job_spec = JobSpec(
        job_num=1,
        job_name=run_spec.run_name + "-1",
        app_specs=job_configurator.app_specs(),
        commands=job_configurator.commands(),
        entrypoint=job_configurator.entrypoint(),
        env=job_configurator.env(),
        gateway=job_configurator.gateway(),
        home_dir=job_configurator.home_dir(),
        image_name=job_configurator.image_name(),
        max_duration=job_configurator.max_duration(),
        registry_auth=job_configurator.registry_auth(),
        requirements=job_configurator.requirements(),
        retry_policy=job_configurator.retry_policy(),
        spot_policy=job_configurator.spot_policy(),
        working_dir=job_configurator.working_dir(),
    )
    return [job_spec]


def _get_job_configurator(run_spec: RunSpec) -> JobConfigurator:
    configuration_type = ConfigurationType(run_spec.configuration.type)
    configurator_class = _configuration_type_to_configurator_class_map[configuration_type]
    return configurator_class(run_spec)


_job_configurator_classes = [
    DevEnvironmentJobConfigurator,
]

_configuration_type_to_configurator_class_map = {c.TYPE: c for c in _job_configurator_classes}
