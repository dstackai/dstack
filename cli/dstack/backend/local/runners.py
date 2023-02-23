import os
import platform
import shutil
import signal
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

import cpuinfo
import psutil
import requests
import yaml
from psutil import NoSuchProcess
from tqdm import tqdm

from dstack import version
from dstack.core.job import Job, JobStatus, Requirements
from dstack.core.request import RequestHead, RequestStatus
from dstack.core.runners import Gpu, Resources, Runner

CREATE_INSTANCE_RETRY_RATE_SECS = 3


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
        cpus=data["cpus"],
        memory_mib=data["memory_mib"],
        gpus=[Gpu(name=g["name"], memory_mib=g["memory_mib"]) for g in data["gpus"]]
        if data.get("gpus")
        else [],
        interruptible=False,
        local=True,
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


def get_request_head(job: Job, request_id: Optional[str]) -> RequestHead:
    if request_id is None:
        return RequestHead(
            job_id=job.job_id, status=RequestStatus.TERMINATED, message="PID is not specified"
        )
    _running = is_running(request_id)
    return RequestHead(
        job_id=job.job_id,
        status=RequestStatus.RUNNING if _running else RequestStatus.TERMINATED,
        message=None,
    )


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
