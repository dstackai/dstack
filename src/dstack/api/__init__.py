from dstack._internal.core.errors import ClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import RegistryAuth
from dstack._internal.core.models.configurations import (
    ServiceConfiguration as _ServiceConfiguration,
)
from dstack._internal.core.models.configurations import TaskConfiguration as _TaskConfiguration
from dstack._internal.core.models.profiles import ProfileDisk as _ProfileDisk
from dstack._internal.core.models.profiles import ProfileGPU as _ProfileGPU
from dstack._internal.core.models.profiles import ProfileResources as _ProfileResources
from dstack._internal.core.models.repos.local import LocalRepo
from dstack._internal.core.models.repos.remote import RemoteRepo
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.core.services.ssh.ports import PortUsedError
from dstack.api._public import BackendCollection, Client, RepoCollection, RunCollection
from dstack.api._public.backends import Backend
from dstack.api._public.huggingface.completions import CompletionService, CompletionTask
from dstack.api._public.huggingface.finetuning.sft import FineTuningTask
from dstack.api._public.runs import Run, RunStatus

GPU = _ProfileGPU
Disk = _ProfileDisk
Resources = _ProfileResources
Service = _ServiceConfiguration
Task = _TaskConfiguration
