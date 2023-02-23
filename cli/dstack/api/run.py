from collections import defaultdict
from typing import List, Optional, Tuple

from dstack.api.repo import load_repo_data
from dstack.backend.base import Backend
from dstack.core.repo import RepoData
from dstack.core.run import RunHead
from dstack.core.tag import TagHead


class RunNotFoundError(Exception):
    pass


class TagNotFoundError(Exception):
    pass


def list_runs_with_merged_backends(
    backends: List[Backend], run_name: str = "", all: bool = False
) -> List[Tuple[RunHead, List[Backend]]]:
    runs = list_runs(backends, run_name, all)
    run_name_to_run_map = {r.run_name: r for r, _ in runs}

    run_name_to_backends_map = defaultdict(list)
    for run, backend in runs:
        run_name_to_backends_map[run.run_name].append(backend)

    runs_with_merged_backends = []
    for run_name in run_name_to_run_map:
        runs_with_merged_backends.append(
            (
                run_name_to_run_map[run_name],
                list(sorted(run_name_to_backends_map[run_name], key=lambda b: b.name)),
            )
        )
    return runs_with_merged_backends


def list_runs(
    backends: List[Backend], run_name: str = "", all: bool = False
) -> List[Tuple[RunHead, Backend]]:
    repo_data = load_repo_data()
    runs = []
    for backend in backends:
        runs += [(run, backend) for run in _get_runs(repo_data, backend, run_name, all)]
    return list(sorted(runs, key=lambda r: -r[0].submitted_at))


def _get_runs(
    repo_data: RepoData, backend: Backend, run_name: str = "", all: bool = False
) -> List[RunHead]:
    runs = []
    runs_backend = backend.list_run_heads(repo_data, run_name)
    for run in runs_backend:
        runs.append(run)
    if not all:
        unfinished = any(run.status.is_unfinished() for run in runs)
        if unfinished:
            runs = list(filter(lambda r: r.status.is_unfinished(), runs))
        else:
            runs = runs[:1]
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
