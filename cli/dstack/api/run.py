from typing import List, Union
from dstack.backend import Backend
from dstack.core.run import RunHead
from dstack.api.repo import load_repo_data


def list_runs(backends: Union[List[Backend], Backend], run_name: str = "", all: bool = False) -> List[RunHead]:
    repo_data = load_repo_data()
    runs = []
    if type(backends) == list:
        for backend in backends:
            job_heads = backend.list_job_heads(repo_data, run_name)
            runs_backend = backend.get_run_heads(repo_data, job_heads)
            for run in runs_backend:
                run.backend_name = backend.name
                runs.append(run)
    else:
        job_heads = backends.list_job_heads(repo_data, run_name)
        runs_backend = backends.get_run_heads(repo_data, job_heads)
        for run in runs_backend:
            run.backend_name = backends.name
            runs.append(run)
    if not all:
        unfinished = any(run.status.is_unfinished() for run in runs)
        if unfinished:
            runs = list(filter(lambda r: r.status.is_unfinished(), runs))
        else:
            runs = runs[:1]
    runs = reversed(runs)
    return runs
