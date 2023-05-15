from typing import List, Optional, Tuple

from dstack.api.hub import HubClient
from dstack.backend.base import Backend
from dstack.core.run import RunHead
from dstack.core.tag import TagHead


class RunNotFoundError(Exception):
    pass


class TagNotFoundError(Exception):
    pass


def list_runs(hub_client: HubClient, run_name: str = "", all: bool = False) -> List[RunHead]:
    runs = [run for run in _get_runs(hub_client, run_name, all)]
    return list(sorted(runs, key=lambda r: -r.submitted_at))


def _get_runs(hub_client: HubClient, run_name: str = "", all: bool = False) -> List[RunHead]:
    runs = hub_client.list_run_heads(run_name)
    if not all:
        unfinished = any(run.status.is_unfinished() for run in runs)
        if unfinished:
            runs = list(filter(lambda r: r.status.is_unfinished(), runs))
        else:
            runs = runs[:1]
    return runs


def get_tagged_run_name(
    hub_client: HubClient, run_name_or_tag_name: str
) -> Tuple[str, Optional[TagHead]]:
    if run_name_or_tag_name.startswith(":"):
        tag_name = run_name_or_tag_name[1:]
        tag_head = hub_client.get_tag_head(tag_name)
        if tag_head is not None:
            return tag_head.run_name, tag_head
        else:
            raise TagNotFoundError()
    else:
        run_name = run_name_or_tag_name
        job_heads = hub_client.list_job_heads(run_name)
        if job_heads:
            return run_name, None
        else:
            raise RunNotFoundError()
