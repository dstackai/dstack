from typing import List, Union
from dstack.backend import Backend
from dstack.core.run import RunHead
from dstack.core.repo import RepoData
from dstack.api.repo import load_repo_data


def get_runs(repo_data: RepoData, backend: Backend, run_name: str = "", all: bool = False) -> List[RunHead]:
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


def list_runs(backends: Union[List[Backend], Backend], run_name: str = "", all: bool = False) -> List[RunHead]:
    repo_data = load_repo_data()
    runs = []
    if type(backends) == list:
        for backend in backends:
           runs = runs + [run for run in get_runs(repo_data, backend, run_name, all)]
    else:
        runs = runs + [run for run in get_runs(repo_data, backends, run_name, all)]
    runs = reversed(runs)
    return runs
