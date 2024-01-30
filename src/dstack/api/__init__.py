# ruff: noqa: F401
from dstack._internal.core.errors import ClientError
from dstack._internal.core.models.backends.base import BackendType
from dstack._internal.core.models.configurations import RegistryAuth
from dstack._internal.core.models.configurations import (
    ServiceConfiguration as _ServiceConfiguration,
)
from dstack._internal.core.models.configurations import TaskConfiguration as _TaskConfiguration
from dstack._internal.core.models.gateways import OpenAIChatModel, TGIChatModel
from dstack._internal.core.models.repos.local import LocalRepo
from dstack._internal.core.models.repos.remote import RemoteRepo
from dstack._internal.core.models.repos.virtual import VirtualRepo
from dstack._internal.core.services.ssh.ports import PortUsedError
from dstack.api._public import BackendCollection, Client, RepoCollection, RunCollection
from dstack.api._public.backends import Backend
from dstack.api._public.huggingface.completions import CompletionService, CompletionTask
from dstack.api._public.huggingface.finetuning.sft import FineTuningTask
from dstack.api._public.resources import GPU, Disk, Resources
from dstack.api._public.runs import Run, RunStatus

Service = _ServiceConfiguration
Task = _TaskConfiguration
