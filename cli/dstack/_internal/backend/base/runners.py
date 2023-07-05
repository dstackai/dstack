from typing import Optional

import yaml

from dstack._internal.backend.base.compute import Compute
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.job import JobStatus
from dstack._internal.core.runners import Resources, Runner


def get_runner(storage: Storage, runner_id: str) -> Optional[Runner]:
    obj = storage.get_object(_get_runner_filename(runner_id))
    if obj is None:
        return None
    return Runner.unserialize(yaml.load(obj, yaml.FullLoader))


def create_runner(storage: Storage, runner: Runner):
    metadata = None
    if runner.job.status == JobStatus.STOPPING:
        metadata = {"status": "stopping"}
    storage.put_object(
        key=_get_runner_filename(runner.runner_id),
        content=yaml.dump(runner.serialize()),
        metadata=metadata,
    )


def update_runner(storage: Storage, runner: Runner):
    create_runner(storage, runner)


def delete_runner(storage: Storage, runner: Runner):
    storage.delete_object(_get_runner_filename(runner.runner_id))


def stop_runner(compute: Compute, runner: Runner):
    if runner.request_id:
        if runner.resources.spot:
            compute.cancel_spot_request(runner)
        else:
            compute.terminate_instance(runner)


def serialize_runner_yaml(
    runner_id: str,
    resources: Resources,
    runner_port_range_from: int,
    runner_port_range_to: int,
):
    s = (
        f"id: {runner_id}\\n"
        f"expose_ports: {runner_port_range_from}-{runner_port_range_to}\\n"
        f"resources:\\n"
    )
    s += f"  cpus: {resources.cpus}\\n"
    if resources.gpus:
        s += "  gpus:\\n"
        for gpu in resources.gpus:
            s += f"    - name: {gpu.name}\\n      memory_mib: {gpu.memory_mib}\\n"
    if resources.spot:
        s += "  spot: true\\n"
    if resources.local:
        s += "  local: true\\n"
    return s[:-2]


def _get_runner_filename(runner_id: str) -> str:
    return f"runners/{runner_id}.yaml"
