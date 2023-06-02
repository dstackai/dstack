import os

from dstack._internal.backend.aws import AwsBackend
from dstack._internal.backend.azure import AzureBackend
from dstack._internal.backend.base import Backend
from dstack._internal.backend.gcp import GCPBackend
from dstack._internal.backend.local import LocalBackend
from dstack._internal.core.job import Job

backend_classes = [AwsBackend, AzureBackend, LocalBackend, GCPBackend]


current_backend = None


def get_current_repo_id() -> str:
    return os.environ["DSTACK_REPO"]


def get_current_run_name() -> str:
    return os.environ["RUN_NAME"]


def get_current_job_id() -> str:
    return os.environ["JOB_ID"]


def get_current_backend() -> Backend:
    global current_backend
    if current_backend is not None:
        return current_backend
    for backend_class in backend_classes:
        backend = backend_class.load()
        if backend is not None:
            current_backend = backend
            return current_backend


current_job = None


def get_current_job() -> Job:
    global current_job
    if current_job is not None:
        return current_job
    backend = get_current_backend()
    current_job = backend.get_job(get_current_repo_id(), get_current_job_id())
    return current_job
