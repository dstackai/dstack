from pathlib import Path
from platform import uname as platform_uname
from typing import Optional

import cpuinfo

from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.build import BuildNotFoundError, BuildPlan, BuildPolicy, DockerPlatform
from dstack._internal.core.job import Job
from dstack._internal.utils.escape import escape_head


def predict_build_plan(
    storage: Storage, job: Job, platform: Optional[DockerPlatform]
) -> BuildPlan:
    if job.build_policy in [BuildPolicy.FORCE_BUILD, BuildPolicy.BUILD_ONLY]:
        return BuildPlan.yes

    if platform is None:
        platform = guess_docker_platform()
    if build_exists(storage, job, platform):
        return BuildPlan.use

    if job.build_commands:
        if job.build_policy == BuildPolicy.USE_BUILD:
            raise BuildNotFoundError("Build not found. Run `dstack build` or add `--build` flag")
        return BuildPlan.yes

    if job.optional_build_commands and job.build_policy == BuildPolicy.BUILD:
        return BuildPlan.yes
    return BuildPlan.no


def build_exists(storage: Storage, job: Job, platform: DockerPlatform) -> bool:
    prefix = _get_build_head_prefix(job, platform)
    return len(storage.list_objects(prefix)) > 0


def _get_build_head_prefix(job: Job, platform: DockerPlatform) -> str:
    parts = [
        job.configuration_type.value,
        job.configuration_path or "",
        (Path("/workflow") / (job.working_dir or "")).as_posix(),
        job.image_name,
        platform.value,
        # digest
        # timestamp_utc
    ]
    parts = ";".join(escape_head(p) for p in parts)
    return f"builds/{job.repo_ref.repo_id}/{parts};"


def guess_docker_platform() -> DockerPlatform:
    uname = platform_uname()
    if uname.system == "Darwin":
        brand = cpuinfo.get_cpu_info().get("brand_raw")
        m_arch = "m1" in brand.lower() or "m2" in brand.lower()
        arch = "arm64" if m_arch else "x86_64"
    else:
        arch = uname.machine
    if uname.system == "Darwin" and arch in ["arm64", "aarch64"]:
        return DockerPlatform.arm64
    return DockerPlatform.amd64
