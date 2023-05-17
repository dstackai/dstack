import time
from pathlib import Path
from typing import List, Optional

from dstack.backend.base import artifacts, jobs, runs
from dstack.backend.base.storage import Storage
from dstack.core.artifact import ArtifactHead, ArtifactSpec
from dstack.core.error import BackendError
from dstack.core.job import Job, JobStatus
from dstack.core.repo import Repo
from dstack.core.tag import TagHead
from dstack.utils.common import get_milliseconds_since_epoch
from dstack.utils.escape import unescape_head


def get_tag_head(storage: Storage, repo_id: str, tag_name: str) -> Optional[TagHead]:
    tag_head_key_prefix = _get_tag_head_filename_prefix(repo_id, tag_name)
    tag_head_keys = storage.list_objects(keys_prefix=tag_head_key_prefix)
    if len(tag_head_keys) == 0:
        return None
    t = tag_head_keys[0][len(tag_head_key_prefix) :].split(";")
    if len(t) == 6:
        (
            run_name,
            workflow_name,
            provider_name,
            hub_user_name,
            created_at,
            artifact_heads,
        ) = tuple(t)
        return TagHead(
            repo_id=repo_id,
            tag_name=tag_name,
            run_name=run_name,
            workflow_name=workflow_name or None,
            provider_name=provider_name or None,
            hub_user_name=hub_user_name or None,
            created_at=int(created_at),
            artifact_heads=_unserialize_artifact_heads(artifact_heads),
        )


def list_tag_heads(storage: Storage, repo_id: str):
    tag_heads_keys_prefix = _get_tag_heads_filenames_prefix(repo_id)
    tag_heads_keys = storage.list_objects(tag_heads_keys_prefix)
    tag_heads = []
    for tag_head_key in tag_heads_keys:
        t = tag_head_key[len(tag_heads_keys_prefix) :].split(";")
        if len(t) == 7:
            (
                tag_name,
                run_name,
                workflow_name,
                provider_name,
                hub_user_name,
                created_at,
                artifact_heads,
            ) = tuple(t)
            tag_heads.append(
                TagHead(
                    repo_id=repo_id,
                    tag_name=tag_name,
                    run_name=run_name,
                    workflow_name=workflow_name or None,
                    provider_name=provider_name or None,
                    hub_user_name=hub_user_name or None,
                    created_at=int(created_at),
                    artifact_heads=_unserialize_artifact_heads(artifact_heads),
                )
            )
    return tag_heads


def delete_tag(
    storage: Storage,
    repo_id: str,
    tag_head: TagHead,
):
    tag_jobs = []
    job_heads = jobs.list_job_heads(storage, repo_id, tag_head.run_name)
    for job_head in job_heads:
        job = jobs.get_job(storage, repo_id, job_head.job_id)
        if job is not None:
            tag_jobs.append(job)
    storage.delete_object(tag_head.key())
    for job in tag_jobs:
        job.tag_name = None
        jobs.update_job(storage, job)


def create_tag_from_run(
    storage: Storage,
    repo_id: str,
    tag_name: str,
    run_name: str,
    run_jobs: Optional[List[Job]],
):
    if run_jobs:
        tag_jobs = run_jobs
    else:
        tag_jobs = []
        job_with_anther_tag = None
        job_heads = jobs.list_job_heads(storage, repo_id, run_name)
        for job_head in job_heads:
            job = jobs.get_job(storage, repo_id, job_head.job_id)
            if job:
                tag_jobs.append(job)
                if job.tag_name and job.tag_name != tag_name:
                    job_with_anther_tag = job
        if job_with_anther_tag:
            raise BackendError(
                f"The run '{job_with_anther_tag.run_name}' refers to another tag: "
                f"'{job_with_anther_tag.tag_name}'"
            )
        if not tag_jobs:
            exit(f"Cannot find the run '{run_name}'")

    tag_head = TagHead(
        repo_id=repo_id,
        tag_name=tag_name,
        run_name=run_name,
        workflow_name=tag_jobs[0].workflow_name,
        provider_name=tag_jobs[0].provider_name,
        hub_user_name=tag_jobs[0].hub_user_name,
        created_at=int(round(time.time() * 1000)),
        artifact_heads=[
            ArtifactHead(job_id=run_job.job_id, artifact_path=artifact_spec.artifact_path)
            for run_job in tag_jobs
            for artifact_spec in run_job.artifact_specs or []
        ]
        or None,
    )
    storage.put_object(key=tag_head.key(), content="")

    if not run_jobs:
        for job in tag_jobs:
            job.tag_name = tag_name
            jobs.update_job(storage, job)


def create_tag_from_local_dirs(
    storage: Storage,
    repo: Repo,
    hub_user_name: str,
    tag_name: str,
    local_dirs: List[str],
):
    local_paths = []
    tag_artifacts = []
    for local_dir in local_dirs:
        path = Path(local_dir)
        if path.is_dir():
            local_paths.append(path)
            tag_artifacts.append(str(path))
        else:
            exit(f"The '{local_dir}' path doesn't refer to an existing directory")

    run_name = runs.create_run(storage)
    job = Job(
        job_id=f"{run_name},,0",
        repo_ref=repo.repo_ref,
        hub_user_name=hub_user_name,
        repo_data=repo.repo_data,
        run_name=run_name,
        workflow_name=None,
        provider_name="bash",
        status=JobStatus.DONE,
        submitted_at=get_milliseconds_since_epoch(),
        image_name="scratch",
        commands=None,
        env=None,
        working_dir=None,
        artifact_specs=[ArtifactSpec(artifact_path=a, mount=False) for a in tag_artifacts],
        cache_specs=[],
        host_name=None,
        requirements=None,
        dep_specs=None,
        master_job=None,
        app_specs=None,
        runner_id=None,
        request_id=None,
        tag_name=tag_name,
    )
    jobs.create_job(storage, job, create_head=False)
    for index, local_path in enumerate(local_paths):
        artifacts.upload_job_artifact_files(
            storage,
            repo.repo_id,
            job.job_id,
            tag_artifacts[index],
            tag_artifacts[index],
            local_path,
        )
    tag_head = TagHead(
        repo_id=repo.repo_id,
        tag_name=tag_name,
        run_name=run_name,
        workflow_name=job.workflow_name,
        provider_name=job.provider_name,
        hub_user_name=hub_user_name,
        created_at=job.submitted_at,
        artifact_heads=[
            ArtifactHead(job_id=job.job_id, artifact_path=a.artifact_path)
            for a in job.artifact_specs
        ]
        if job.artifact_specs
        else None,
    )
    storage.put_object(key=tag_head.key(), content="")


def _get_tags_dir(repo_id: str) -> str:
    return f"tags/{repo_id}/"


def _get_tag_head_filename_prefix(repo_id: str, tag_name: str) -> str:
    prefix = _get_tags_dir(repo_id)
    key = f"{prefix}l;{tag_name};"
    return key


def _get_tag_heads_filenames_prefix(repo_id: str) -> str:
    prefix = _get_tags_dir(repo_id)
    key = f"{prefix}l;"
    return key


def _unserialize_artifact_heads(artifact_heads):
    return (
        [
            ArtifactHead(job_id=a.split("=")[0], artifact_path=unescape_head(a.split("=")[1]))
            for a in artifact_heads.split(":")
        ]
        if artifact_heads
        else None
    )
