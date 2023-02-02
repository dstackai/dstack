from typing import List, Union, Tuple, Optional
from dstack.backend import Backend
from dstack.core.run import RunHead
from dstack.core.repo import RepoData
from dstack.core.tag import TagHead
from dstack.api.repo import load_repo_data


class RunNotFoundError(Exception):
    pass


class TagNotFoundError(Exception):
    pass


def get_runs(
    repo_data: RepoData, backend: Backend, run_name: str = "", all: bool = False
) -> List[RunHead]:
    runs = []
    job_heads = backend.list_job_heads(repo_data, run_name)
    runs_backend = backend.get_run_heads(repo_data, job_heads)
    for run in runs_backend:
        run.backend_name = backend.name
        runs.append(run)
    if not all:
        unfinished = any(run.status.is_unfinished() for run in runs)
        if unfinished:
            runs = list(filter(lambda r: r.status.is_unfinished(), runs))
        else:
            runs = runs[:1]
    return runs


def list_runs(
    backends: Union[List[Backend], Backend], run_name: str = "", all: bool = False
) -> List[RunHead]:
    repo_data = load_repo_data()
    runs = []
    if type(backends) == list:
        for backend in backends:
            runs = runs + [run for run in get_runs(repo_data, backend, run_name, all)]
    else:
        runs = runs + [run for run in get_runs(repo_data, backends, run_name, all)]
    runs = reversed(runs)
    return runs


def get_tagged_run_name(repo_data, backend, run_name_or_tag_name) -> Tuple[str, Optional[TagHead]]:
    if run_name_or_tag_name.startswith(":"):
        tag_name = run_name_or_tag_name[1:]
        tag_head = backend.get_tag_head(repo_data, tag_name)
        if tag_head is not None:
            return tag_head.run_name, tag_head
        else:
            raise TagNotFoundError()
    else:
        run_name = run_name_or_tag_name
        job_heads = backend.list_job_heads(repo_data, run_name)
        if job_heads:
            return run_name, None
        else:
            raise RunNotFoundError()
