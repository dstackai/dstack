import os

import yaml

from dstack._internal.backend.base import Backend
from dstack._internal.backend.base.config import BACKEND_CONFIG_FILEPATH
from dstack._internal.core.error import DstackError
from dstack._internal.core.job import Job


def get_current_backend_type() -> str:
    with open(BACKEND_CONFIG_FILEPATH) as f:
        yaml_content = f.read()
    config = yaml.load(yaml_content, yaml.FullLoader)
    return config["backend"]


current_backend_type = get_current_backend_type()


def get_current_repo_id() -> str:
    return os.environ["DSTACK_REPO"]


def get_current_run_name() -> str:
    return os.environ["RUN_NAME"]


def get_current_job_id() -> str:
    return os.environ["JOB_ID"]


current_backend = None


def get_current_backend() -> Backend:
    global current_backend
    if current_backend is not None:
        return current_backend
    if current_backend_type == "aws":
        try:
            from dstack._internal.backend.aws import AwsBackend as backend_class
        except ImportError:
            raise DstackError(
                "Dependencies for AWS backend are not installed. Run `pip install dstack[aws]`."
            )
    elif current_backend_type == "azure":
        try:
            from dstack._internal.backend.azure import AzureBackend as backend_class
        except ImportError:
            raise DstackError(
                "Dependencies for Azure backend are not installed. Run `pip install dstack[azure]`."
            )
    elif current_backend_type == "gcp":
        try:
            from dstack._internal.backend.gcp import GCPBackend as backend_class
        except ImportError:
            raise DstackError(
                "Dependencies for GCP backend are not installed. Run `pip install dstack[gcp]`."
            )
    elif current_backend_type == "lambda":
        try:
            from dstack._internal.backend.lambdalabs import LambdaBackend as backend_class
        except ImportError:
            raise DstackError(
                "Dependencies for LambdaLabs backend are not installed. Run `pip install dstack[lambda]`."
            )
    elif current_backend_type == "local":
        from dstack._internal.backend.local import LocalBackend as backend_class
    current_backend = backend_class.load()
    return current_backend


current_job = None


def get_current_job() -> Job:
    global current_job
    if current_job is not None:
        return current_job
    backend = get_current_backend()
    current_job = backend.get_job(get_current_repo_id(), get_current_job_id())
    return current_job
