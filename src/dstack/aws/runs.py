from typing import Optional, List

from botocore.client import BaseClient

from dstack import random_name
from dstack.aws import run_names, logs, jobs
from dstack.backend import Run, AppHead, RequestHead, RequestStatus
from dstack.jobs import JobHead, Job


def create_run(s3_client: BaseClient, logs_client: BaseClient, bucket_name: str, repo_user_name: str,
               repo_name: str) -> str:
    name = random_name.next_name()
    run_name_index = run_names.next_run_name_index(s3_client, bucket_name, name)
    run_name = f"{name}-{run_name_index}"
    log_group_name = f"/dstack/jobs/{bucket_name}/{repo_user_name}/{repo_name}"
    logs.create_log_group_if_not_exists(logs_client, bucket_name, log_group_name)
    logs.create_log_stream(logs_client, log_group_name, run_name)
    return run_name


def _request_head(ec2_client: BaseClient, job: Job) -> RequestHead:
    interrupted = job.requirements and job.requirements.interruptible
    if job.request_id:
        if interrupted:
            response = ec2_client.describe_spot_instance_requests(SpotInstanceRequestIds=[job.request_id])
            if response.get("SpotInstanceRequests"):
                status = response["SpotInstanceRequests"][0]["Status"]
                if status["Code"] in ["fulfilled"]:
                    request_status = RequestStatus.RUNNING
                elif status["Code"] in ["not-scheduled-yet", "pending-evaluation", "pending-fulfillment"]:
                    request_status = RequestStatus.PENDING
                elif status["Code"] in ["not-capacity-not-available", "instance-stopped-no-capacity",
                                        "instance-terminated-by-price", "instance-stopped-by-price",
                                        "instance-terminated-no-capacity", "limit-exceeded", "price-too-low"]:
                    request_status = RequestStatus.NO_CAPACITY
                elif status["Code"] in ["instance-terminated-by-user", "instance-stopped-by-user",
                                        "canceled-before-fulfillment", "instance-terminated-by-schedule",
                                        "instance-terminated-by-service", "spot-instance-terminated-by-user",
                                        "marked-for-stop", "marked-for-termination"]:
                    request_status = RequestStatus.TERMINATED
                else:
                    raise Exception(f"Unsupported EC2 spot instance request status code: {status['Code']}")
                return RequestHead(job.job_id, request_status, status.get("Message"))
            else:
                return RequestHead(job.job_id, RequestStatus.TERMINATED, None)
        else:
            response = ec2_client.describe_instances(InstanceIds=[job.request_id])
            if response.get("Reservations") and response["Reservations"][0].get("Instances"):
                state = response["Reservations"][0]["Instances"][0]["State"]
                if state["Name"] in ["running"]:
                    request_status = RequestStatus.RUNNING
                elif state["Name"] in ["pending"]:
                    request_status = RequestStatus.PENDING
                elif state["Name"] in ["shutting-down", "terminated", "stopping", "stopped"]:
                    request_status = RequestStatus.TERMINATED
                else:
                    raise Exception(f"Unsupported EC2 instance state name: {state['Name']}")
                return RequestHead(job.job_id, request_status, None)
            else:
                return RequestHead(job.job_id, RequestStatus.TERMINATED, None)
    else:
        message = "The spot instance request ID is not specified" if interrupted else "The instance ID is not specified"
        return RequestHead(job.job_id, RequestStatus.TERMINATED, message)


def _create_run(ec2_client: BaseClient, repo_user_name, repo_name, job: Job, include_request_heads: bool) -> Run:
    app_heads = list(map(lambda a: AppHead(job.job_id, a), job.app_specs)) if job.app_specs else None
    request_heads = None
    if include_request_heads and job.status.is_unfinished():
        if request_heads is None:
            request_heads = []
        request_heads.append(_request_head(ec2_client, job))
    run = Run(repo_user_name, repo_name, job.run_name, job.workflow_name, job.provider_name,
              job.artifacts or None, job.status, job.submitted_at, job.tag_name,
              app_heads, request_heads)
    return run


def _update_run(ec2_client: BaseClient, run: Run, job: Job, include_request_heads: bool):
    run.submitted_at = min(run.submitted_at, job.submitted_at)
    if job.artifacts:
        if run.artifacts is None:
            run.artifacts = []
        run.artifacts.extend(job.artifacts)
    if job.app_specs:
        if run.app_heads is None:
            run.app_heads = []
        run.app_heads.extend(list(map(lambda a: AppHead(job.job_id, a), job.app_specs)))
    if job.status.is_unfinished():
        run.status = job.status
        if include_request_heads:
            if run.request_heads is None:
                run.request_heads = []
            run.request_heads.append(_request_head(ec2_client, job))


def get_runs(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name,
             job_heads: List[JobHead], include_request_heads: bool) -> List[Run]:
    runs_by_id = {}
    for job_head in job_heads:
        job = jobs.get_job(s3_client, bucket_name, repo_user_name, repo_name, job_head.job_id)
        run_id = ','.join([job.run_name, job.workflow_name or ''])
        if run_id not in runs_by_id:
            runs_by_id[run_id] = _create_run(ec2_client, repo_user_name, repo_name, job, include_request_heads)
        else:
            run = runs_by_id[run_id]
            _update_run(ec2_client, run, job, include_request_heads)
    return sorted(list(runs_by_id.values()), key=lambda r: r.submitted_at, reverse=True)


def list_runs(ec2_client: BaseClient, s3_client: BaseClient, bucket_name: str, repo_user_name, repo_name,
              run_name: Optional[str], include_request_heads: bool) -> List[Run]:
    job_heads = jobs.list_job_heads(s3_client, bucket_name, repo_user_name, repo_name, run_name)
    return get_runs(ec2_client, s3_client, bucket_name, repo_user_name, repo_name, job_heads, include_request_heads)
