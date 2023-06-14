import os
import platform
import shutil
import signal
import subprocess
from pathlib import Path
from typing import Optional

import cpuinfo
import psutil
import requests
import yaml
from psutil import NoSuchProcess
from tqdm import tqdm

from dstack import version
from dstack._internal.backend.base.config import BACKEND_CONFIG_FILENAME, RUNNER_CONFIG_FILENAME
from dstack._internal.backend.local.config import LocalConfig
from dstack._internal.core.job import Job
from dstack._internal.core.request import RequestHead, RequestStatus
from dstack._internal.core.runners import Gpu, Resources


def start_runner_process(backend_config: LocalConfig, runner_id: str) -> str:
    _install_runner_if_necessary()
    runner_config_dir = _get_runner_config_dir(backend_config, runner_id)
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


def check_runner_resources(backend_config: LocalConfig, runner_id: str) -> Resources:
    _install_runner_if_necessary()
    runner_config_dir = _get_runner_config_dir(backend_config, runner_id, create=True)
    backend_config_path = runner_config_dir / BACKEND_CONFIG_FILENAME
    with open(backend_config_path, "w+") as f:
        f.write(backend_config.serialize_yaml())
    runner_config_path = runner_config_dir / RUNNER_CONFIG_FILENAME
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
        spot=False,
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


def _download_runner(url: str, path: Path):
    runner_download_path = path.parent / "runner-download"
    with requests.get(url, stream=True) as r:
        total_length = int(r.headers.get("Content-Length"))
        with tqdm.wrapattr(r.raw, "read", total=total_length, desc=f"Downloading runner") as raw:
            with open(runner_download_path, "wb") as output:
                shutil.copyfileobj(raw, output)
    shutil.move(runner_download_path, path)
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


def _get_runner_config_dir(
    backend_config: LocalConfig, runner_id: str, create: Optional[bool] = None
) -> Path:
    runner_config_dir_path = backend_config.backend_dir / "tmp" / "runner" / "configs" / runner_id
    if create:
        runner_config_dir_path.mkdir(parents=True, exist_ok=True)
        runner_config_path = runner_config_dir_path / RUNNER_CONFIG_FILENAME
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
    amd64 = arch in ["x86_64", "AMD64"]
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
    elif windows and amd64:
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
