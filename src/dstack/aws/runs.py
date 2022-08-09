from botocore.client import BaseClient

from dstack import random_name
from dstack.aws import run_names, logs


def create_run(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str, repo_user_name: str,
               repo_name: str) -> str:
    name = random_name.next_name()
    run_name_index = run_names.next_run_name_index(s3_client, bucket_name, name)
    run_name = f"{name}-{run_name_index}"
    log_group_name = f"/dstack/jobs/{bucket_name}/{repo_user_name}/{repo_name}"
    logs.create_log_group_if_not_exists(logs_client, bucket_name, log_group_name)
    logs.create_log_stream(logs_client, log_group_name, run_name)
    return run_name
