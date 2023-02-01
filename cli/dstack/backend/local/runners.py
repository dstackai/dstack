import sys
import os
import uuid
import signal
from typing import List, Optional, Tuple
import subprocess
import platform
import cpuinfo

from tqdm import tqdm
import psutil
import requests
import yaml
from pathlib import Path

from psutil import NoSuchProcess
import shutil
from dstack import version
from dstack.backend.local import jobs, logs
from dstack.core.instance import InstanceType
from dstack.core.request import RequestStatus, RequestHead
from dstack.core.job import Job, JobStatus, Requirements
from dstack.core.repo import RepoAddress
from dstack.core.runners import Resources, Runner, Gpu
from dstack.backend.local.common import (
    list_objects,
    put_object,
    get_object,
    delete_object,
)

CREATE_INSTANCE_RETRY_RATE_SECS = 3


def _create_runner(path: str, runner: Runner):
    root = os.path.join(path, "runners")
    key = f"{runner.runner_id}.yaml"
    if runner.job.status == JobStatus.STOPPING:
        put_object(Root=root, Key=f"m;{runner.runner_id};status", Body="stopping")
    put_object(Body=yaml.dump(runner.serialize()), Root=root, Key=key)


def _delete_runner(path: str, runner: Runner):
    root = os.path.join(path, "runners")
    key = f"{runner.runner_id}.yaml"
    delete_object(Root=root, Key=key)


def _get_runner(path: str, runner_id: str) -> Optional[Runner]:
    root = os.path.join(path, "runners")
    key = f"{runner_id}.yaml"
    try:
        obj = get_object(Root=root, Key=key)
        return Runner.unserialize(yaml.load(obj, yaml.FullLoader))
    except Exception as e:
        return None


def _update_runner(path: str, runner: Runner):
    root = os.path.join(path, "runners")
    key = f"{runner.runner_id}.yaml"
    if runner.job.status == JobStatus.STOPPING:
        put_object(Root=root, Key=f"m;{runner.runner_id};status", Body="stopping")
    put_object(Body=yaml.dump(runner.serialize()), Root=root, Key=key)


def _matches(resources: Resources, requirements: Optional[Requirements]) -> bool:
    if not requirements:
        return True
    if requirements.cpus and requirements.cpus > resources.cpus:
        return False
    if requirements.memory_mib and requirements.memory_mib > resources.memory_mib:
        return False
    if requirements.gpus:
        gpu_count = requirements.gpus.count or 1
        if gpu_count > len(resources.gpus or []):
            return False
        if requirements.gpus.name and gpu_count > len(
            list(filter(lambda gpu: gpu.name == requirements.gpus.name, resources.gpus or []))
        ):
            return False
        if requirements.gpus.memory_mib and gpu_count > len(
            list(
                filter(
                    lambda gpu: gpu.memory_mib >= requirements.gpus.memory_mib,
                    resources.gpus or [],
                )
            )
        ):
            return False
        if requirements.interruptible and not resources.interruptible:
            return False
    return True


def run_job(path: str, job: Job):
    if job.status == JobStatus.SUBMITTED:
        runner = None
        try:
            job.runner_id = uuid.uuid4().hex
            jobs.update_job(path, job)
            resources = check_runner_resources(job.runner_id)
            runner = Runner(job.runner_id, None, resources, job)
            _create_runner(path, runner)
            runner.request_id = start_runner_process(job.runner_id)

            _update_runner(path, runner)
        except Exception as e:
            job.status = JobStatus.FAILED
            job.request_id = runner.request_id if runner else None
            jobs.update_job(path, job)
            raise e
    else:
        raise Exception("Can't create a request for a job which status is not SUBMITTED")


def start_runner_process(runner_id: str) -> str:
    _install_runner_if_necessary()
    runner_config_dir = _get_runner_config_dir(runner_id)
    proc = subprocess.Popen(
        [
            _runner_path(),
            "--config-dir",
            runner_config_dir,
            "--log-level",
            "6",
            "start",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return f"l-{proc.pid}"


def check_runner_resources(runner_id: str) -> Resources:
    _install_runner_if_necessary()
    runner_config_dir = _get_runner_config_dir(runner_id, create=True)
    runner_config_path = runner_config_dir / "runner.yaml"
    result = subprocess.run(
        [f"{_runner_path()} --config-dir {runner_config_dir} check"],
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode > 0:
        raise Exception(result.stderr)
    _runner_yaml = yaml.load(runner_config_path.open(), yaml.FullLoader)
    return _unserialize_runner_resources(_runner_yaml["resources"])


def _unserialize_runner_resources(data: dict) -> Resources:
    return Resources(
        data["cpus"],
        data["memory_mib"],
        [Gpu(g["name"], g["memory_mib"]) for g in data["gpus"]] if data.get("gpus") else [],
        False,
        True,
    )


def _runner_version() -> str:
    runner_version = str(version.__version__) if version.__version__ else "latest"
    return runner_version


runner_bucket_region = "eu-west-1"


def _install_runner_if_necessary():
    runner_path = _runner_path()
    if not runner_path.exists():
        runner_path.parent.mkdir(parents=True, exist_ok=True)
        _download_runner(_runner_url(), runner_path)


def _download_runner(url: str, path: str):
    with requests.get(url, stream=True) as r:
        total_length = int(r.headers.get("Content-Length"))

        with tqdm.wrapattr(r.raw, "read", total=total_length, desc=f"Downloading runner") as raw:
            with open(path, "wb") as output:
                shutil.copyfileobj(raw, output)
        os.chmod(path, 0o755)


def _runner_url() -> str:
    return (
        f"https://{_runner_bucket()}.s3.{runner_bucket_region}.amazonaws.com"
        f"/{_runner_version()}/binaries/{_runner_filename()}"
    )


def _runner_bucket() -> str:
    if version.__is_release__:
        return "dstack-runner-downloads"
    else:
        return "dstack-runner-downloads-stgn"


def _get_runner_config_dir(runner_id: str, create: Optional[bool] = None) -> str:
    runner_config_dir_path = Path(
        os.path.join(_config_directory_path(), "tmp", "runner", "configs", runner_id)
    )
    if create:
        runner_config_dir_path.mkdir(parents=True, exist_ok=True)
        runner_config_path = runner_config_dir_path / "runner.yaml"
        runner_config_path.write_text(
            yaml.dump(
                {
                    "id": runner_id,
                    "hostname": "127.0.0.1",
                }
            )
        )
    return runner_config_dir_path


def get_request_head(path: str, job: Job, runner: Optional[Runner] = None) -> RequestHead:
    request_id = None
    if job.request_id:
        request_id = job.request_id
    elif runner and runner.request_id:
        request_id = runner.request_id
    elif not runner:
        runner = _get_runner(path, job.runner_id)
        if runner:
            request_id = runner.request_id
    if request_id:
        _running = is_running(request_id)
        return RequestHead(
            job.job_id,
            RequestStatus.RUNNING if _running else RequestStatus.TERMINATED,
            None,
        )
    else:
        return RequestHead(job.job_id, RequestStatus.TERMINATED, "PID is not specified")


def _stop_runner(path: str, runner: Runner):
    if runner.request_id:
        stop_process(runner.request_id)
    _delete_runner(path, runner)


def _arch() -> str:
    uname = platform.uname()
    if uname.system == "Darwin":
        brand = cpuinfo.get_cpu_info().get("brand_raw")
        m_arch = "m1" in brand.lower() or "m2" in brand.lower()
        arch = "arm64" if m_arch else "x86_64"
    else:
        arch = uname.machine
    return arch


def _runner_filename() -> str:
    uname = platform.uname()
    arch = _arch()
    darwin = uname.system == "Darwin"
    windows = uname.system == "Windows"
    linux = uname.system == "Linux"
    arm64 = arch == "arm64" or arch == "aarch64"
    i386 = arch == "i386"
    amd64 = arch == "x86_64"
    if darwin and arm64:
        filename = "dstack-runner-darwin-arm64"
    elif darwin and amd64:
        filename = "dstack-runner-darwin-amd64"
    elif linux and i386:
        filename = "dstack-runner-linux-x86"
    elif linux and amd64:
        filename = "dstack-runner-linux-amd64"
    elif windows and i386:
        filename = "dstack-runner-windows-x86.exe"
    elif linux and amd64:
        filename = "dstack-runner-windows-amd64.exe"
    else:
        raise Exception(f"Unsupported platform: {uname}")
    return filename


def _config_directory_path() -> Path:
    return Path.home() / ".dstack"


def _runner_path() -> Path:
    return (
        _config_directory_path()
        / "tmp"
        / "runner"
        / "bin"
        / _runner_version()
        / _runner_filename()
    )


def stop_job(path: str, repo_address: RepoAddress, job_id: str, abort: bool):
    job_head = jobs.list_job_head(path, repo_address, job_id)
    job = jobs.get_job(path, repo_address, job_id)
    runner = _get_runner(path, job.runner_id) if job else None
    request_status = (
        get_request_head(path, job, runner).status if job else RequestStatus.TERMINATED
    )
    if (
        job_head
        and job_head.status.is_unfinished()
        or job
        and job.status.is_unfinished()
        or runner
        and runner.job.status.is_unfinished()
        or request_status != RequestStatus.TERMINATED
    ):
        if abort:
            new_status = JobStatus.ABORTED
        elif (
            not job_head
            or job_head.status in [JobStatus.SUBMITTED, JobStatus.DOWNLOADING]
            or not job
            or job.status in [JobStatus.SUBMITTED, JobStatus.DOWNLOADING]
            or request_status == RequestStatus.TERMINATED
            or not runner
        ):
            new_status = JobStatus.STOPPED
        elif (
            job_head
            and job_head.status != JobStatus.UPLOADING
            or job
            and job.status != JobStatus.UPLOADING
        ):
            new_status = JobStatus.STOPPING
        else:
            new_status = None
        if new_status:
            if runner and runner.job.status.is_unfinished() and runner.job.status != new_status:
                if new_status.is_finished():
                    _stop_runner(path, runner)
                else:
                    runner.job.status = new_status
                    _update_runner(path, runner)
            if (
                job_head
                and job_head.status.is_unfinished()
                and job_head.status != new_status
                or job
                and job.status.is_unfinished()
                and job.status != new_status
            ):
                job.status = new_status
                jobs.update_job(path, job)


def stop_process(request_id: str):
    t = request_id.split("-")
    pid = int(t[1])
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass


def is_running(request_id: str) -> bool:
    t = request_id.split("-")
    pid = int(t[1])
    try:
        psutil.Process(pid)
        return True
    except NoSuchProcess:
        return False
