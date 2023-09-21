from datetime import timezone
from typing import List

from dstack._internal.core.models.configurations import ConfigurationType
from dstack._internal.core.models.runs import Job, JobProvisioningData, JobSubmission, RunSpec
from dstack._internal.server.models import JobModel
from dstack._internal.server.services.jobs.configurators.base import JobConfigurator
from dstack._internal.server.services.jobs.configurators.dev import DevEnvironmentJobConfigurator


def get_jobs_from_run_spec(run_spec: RunSpec) -> List[Job]:
    job_configurator = _get_job_configurator(run_spec)
    job_specs = job_configurator.get_job_specs()
    return [Job(job_spec=s, job_submissions=[]) for s in job_specs]


def get_job_specs_from_run_spec(run_spec: RunSpec) -> List[Job]:
    job_configurator = _get_job_configurator(run_spec)
    job_specs = job_configurator.get_job_specs()
    return job_specs


def job_model_to_job_submission(job_model: JobModel) -> JobSubmission:
    job_provisioning_data = None
    if job_model.job_provisioning_data is not None:
        job_provisioning_data = JobProvisioningData.parse_raw(job_model.job_provisioning_data)
    return JobSubmission(
        id=job_model.id,
        submission_num=job_model.submission_num,
        submitted_at=job_model.submitted_at.replace(tzinfo=timezone.utc),
        status=job_model.status,
        error_code=job_model.error_code,
        job_provisioning_data=job_provisioning_data,
    )


def _get_job_configurator(run_spec: RunSpec) -> JobConfigurator:
    configuration_type = ConfigurationType(run_spec.configuration.type)
    configurator_class = _configuration_type_to_configurator_class_map[configuration_type]
    return configurator_class(run_spec)


_job_configurator_classes = [
    DevEnvironmentJobConfigurator,
]

_configuration_type_to_configurator_class_map = {c.TYPE: c for c in _job_configurator_classes}
