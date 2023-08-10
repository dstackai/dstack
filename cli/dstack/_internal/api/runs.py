from typing import List, Optional, Tuple

from dstack._internal.backend.base import Backend
from dstack._internal.core.error import DstackError
from dstack._internal.core.tag import TagHead
from dstack._internal.hub.schemas import RunInfo
from dstack.api.hub import HubClient


class RunNotFoundError(DstackError):
    pass


class TagNotFoundError(DstackError):
    pass


def list_runs_hub(hub_client: HubClient, run_name: str = "", all: bool = False) -> List[RunInfo]:
    runs = hub_client.list_runs(run_name)
    if not all:
        active = any(run.run_head.status.is_active() for run in runs)
        if active:
            runs = list(filter(lambda r: r.run_head.status.is_active(), runs))
        else:
            runs = runs[:1]
    return runs


def get_tagged_run_name_hub(
    hub_client: HubClient, run_name_or_tag_name: str
) -> Tuple[str, Optional[TagHead]]:
    if run_name_or_tag_name.startswith(":"):
        tag_name = run_name_or_tag_name[1:]
        tag_head = hub_client.get_tag_head(tag_name)
        if tag_head is not None:
            return tag_head.run_name, tag_head
        else:
            raise TagNotFoundError(f"Tag {tag_name} not found")
    else:
        run_name = run_name_or_tag_name
        job_heads = hub_client.list_job_heads(run_name)
        if job_heads:
            return run_name, None
        else:
            raise RunNotFoundError(f"Run {run_name} not found")


def get_tagged_run_name_backend(
    backend: Backend, repo_id: str, run_name: Optional[str], tag_name: Optional[str]
) -> Tuple[str, Optional[TagHead]]:
    if run_name is None and tag_name is None:
        raise DstackError("Run or tag must be specified")
    if run_name is not None:
        job_heads = backend.list_job_heads(repo_id=repo_id, run_name=run_name)
        if len(job_heads) == 0:
            raise RunNotFoundError(f"Run {run_name} not found")
        return run_name, None
    tag_head = backend.get_tag_head(repo_id=repo_id, tag_name=tag_name)
    if tag_head is None:
        raise TagNotFoundError(f"Tag {tag_name} not found")
    return tag_head.run_name, tag_head
