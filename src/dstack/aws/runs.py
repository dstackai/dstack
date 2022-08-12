from typing import Optional, List

from botocore.client import BaseClient

from dstack import random_name
from dstack.aws import run_names, logs, jobs
from dstack.backend import Run, RunApp


def create_run(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str, repo_user_name: str,
               repo_name: str) -> str:
    name = random_name.next_name()
    run_name_index = run_names.next_run_name_index(s3_client, bucket_name, name)
    run_name = f"{name}-{run_name_index}"
    log_group_name = f"/dstack/jobs/{bucket_name}/{repo_user_name}/{repo_name}"
    logs.create_log_group_if_not_exists(logs_client, bucket_name, log_group_name)
    logs.create_log_stream(logs_client, log_group_name, run_name)
    return run_name


def get_runs(s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name, run_name: Optional[str]) -> List[Run]:
    runs_by_id = {}
    job_heads = jobs.get_job_heads(s3_client, bucket_name, repo_user_name, repo_name, run_name)
    for job_head in job_heads:
        run_id = ','.join([job_head.run_name, job_head.workflow_name or ''])
        if run_id not in runs_by_id:
            run_apps = list(map(lambda a: RunApp(job_head.get_id(), a), job_head.apps)) if job_head.apps else None
            run = Run(repo_user_name, repo_name, job_head.run_name, job_head.workflow_name, job_head.provider_name,
                      job_head.artifacts or None, job_head.status, job_head.submitted_at, job_head.tag_name,
                      run_apps, None)
            runs_by_id[run_id] = run
        else:
            run = runs_by_id[run_id]
            run.submitted_at = min(run.submitted_at, job_head.submitted_at)
            if job_head.artifacts:
                if run.artifacts is None:
                    run.artifacts = []
                run.artifacts.extend(job_head.artifacts)
            if job_head.apps:
                if run.apps is None:
                    run.apps = []
                run.apps.extend(list(map(lambda a: RunApp(job_head.get_id(), a), job_head.apps)))
            if job_head.status.is_unfinished():
                # TODO: implement max(status1, status2)
                run.status = job_head.status

    runs = list(runs_by_id.values())
    return sorted(runs, key=lambda r: r.submitted_at, reverse=True)
