from typing import Optional

import yaml

from dstack.backend.base.compute import Compute
from dstack.backend.base.storage import Storage
from dstack.core.job import JobStatus
from dstack.core.runners import Runner


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


def stop_runner(storage: Storage, compute: Compute, runner: Runner):
    if runner.request_id:
        if runner.resources.interruptible:
            compute.cancel_spot_request(runner.request_id)
        else:
            compute.terminate_instance(runner.request_id)
    delete_runner(storage, runner)


def _get_runner_filename(runner_id: str) -> str:
    return f"runners/{runner_id}.yaml"
