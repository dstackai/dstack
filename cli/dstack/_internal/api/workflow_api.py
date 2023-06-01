from dstack._internal.backend.base import Backend
from dstack._internal.backend.gcp import GCPBackend
from dstack._internal.core.job import Job

backend_classes = [GCPBackend]


current_backend = None


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
    current_job = backend.get_job()
    return current_job
