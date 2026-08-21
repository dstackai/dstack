import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

from dstack._internal.core.errors import ConfigurationError
from dstack._internal.core.models.configurations import TaskConfiguration
from dstack._internal.core.models.logs import JobSubmissionLogs, LogEvent, LogEventSource
from dstack._internal.core.models.resources import ResourcesSpec
from dstack._internal.core.models.runs import (
    Job,
    JobSpec,
    JobStatus,
    JobSubmission,
    Requirements,
    RunSpec,
    RunStatus,
)
from dstack._internal.core.models.runs import Run as RunModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack.api._public.runs import Run, RunCollection
from tests._internal.utils.test_ssh import PRIVATE_KEY, PUBLIC_KEY, PUBLIC_KEY_NO_COMMENT


class _RunsAPI:
    def __init__(self):
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return []
        return ["finished-run"]


class _APIClient:
    def __init__(self):
        self.runs = _RunsAPI()


class _PlansAPI:
    def __init__(self):
        self.run_specs: list[RunSpec] = []

    def get_plan(self, project_name: str, run_spec: RunSpec, **kwargs) -> str:
        self.run_specs.append(run_spec)
        return "run-plan"


class _PlansAPIClient:
    def __init__(self):
        self.runs = _PlansAPI()


class TestRunCollectionList:
    def test_default_list_fallback_limits_job_submissions(self):
        api_client = _APIClient()
        runs = RunCollection(api_client=api_client, project="main", client=None)
        runs._model_to_run = lambda run: run

        assert runs.list() == ["finished-run"]

        assert api_client.runs.calls[0]["job_submissions_limit"] == 1
        assert api_client.runs.calls[1]["job_submissions_limit"] == 1


class _LogsAPI:
    def __init__(self, logs_by_job_submission_id: dict[uuid.UUID, list[bytes]]):
        self._logs_by_job_submission_id = logs_by_job_submission_id
        self.requests: list[PollLogsRequest] = []

    def poll(self, project_name: str, body: PollLogsRequest) -> JobSubmissionLogs:
        self.requests.append(body)
        messages = self._logs_by_job_submission_id.get(body.job_submission_id, [])
        return JobSubmissionLogs(
            logs=[
                LogEvent(
                    timestamp=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                    log_source=LogEventSource.STDOUT,
                    message=base64.b64encode(message).decode(),
                )
                for message in messages
            ]
        )


def _get_job(replica_num: int, status: JobStatus, job_num: int = 0) -> Job:
    return Job(
        job_spec=JobSpec(
            replica_num=replica_num,
            job_num=job_num,
            job_name=f"test-run-{replica_num}-{job_num}",
            commands=["echo hello"],
            env={},
            image_name="ubuntu:latest",
            requirements=Requirements(resources=ResourcesSpec()),
        ),
        job_submissions=[
            JobSubmission(
                id=uuid.uuid4(),
                submission_num=0,
                submitted_at=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                last_processed_at=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
                status=status,
            )
        ],
    )


def _get_run_model(status: RunStatus, jobs: list[Job]) -> RunModel:
    return RunModel(
        id=uuid.uuid4(),
        project_name="main",
        user="test",
        submitted_at=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        last_processed_at=datetime(2023, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        status=status,
        run_spec=RunSpec(
            run_name="test-run",
            configuration=TaskConfiguration(commands=["echo hello"], image="ubuntu:latest"),
        ),
        jobs=jobs,
    )


def _get_run(run_model: RunModel, logs_api: _LogsAPI) -> Run:
    api_client = _APIClient()
    api_client.logs = logs_api
    return Run(api_client=api_client, project="main", run=run_model)


class TestRunLogs:
    def test_returns_logs_of_finished_run(self):
        job = _get_job(replica_num=0, status=JobStatus.DONE)
        run_model = _get_run_model(status=RunStatus.DONE, jobs=[job])
        job_submission_id = job.job_submissions[-1].id
        logs_api = _LogsAPI({job_submission_id: [b"hello\n"]})
        run = _get_run(run_model, logs_api)

        assert b"".join(run.logs()) == b"hello\n"
        assert [r.job_submission_id for r in logs_api.requests] == [job_submission_id]

    def test_prefers_running_replica(self):
        terminated_job = _get_job(replica_num=0, status=JobStatus.TERMINATED)
        running_job = _get_job(replica_num=1, status=JobStatus.RUNNING)
        run_model = _get_run_model(status=RunStatus.RUNNING, jobs=[terminated_job, running_job])
        logs_api = _LogsAPI(
            {
                terminated_job.job_submissions[-1].id: [b"old replica\n"],
                running_job.job_submissions[-1].id: [b"new replica\n"],
            }
        )
        run = _get_run(run_model, logs_api)

        assert b"".join(run.logs()) == b"new replica\n"

    def test_returns_logs_of_lowest_numbered_replica_if_no_replica_is_running(self):
        replica_1_job = _get_job(replica_num=1, status=JobStatus.TERMINATED)
        replica_0_job = _get_job(replica_num=0, status=JobStatus.TERMINATED)
        run_model = _get_run_model(
            status=RunStatus.TERMINATED, jobs=[replica_1_job, replica_0_job]
        )
        logs_api = _LogsAPI(
            {
                replica_1_job.job_submissions[-1].id: [b"replica 1\n"],
                replica_0_job.job_submissions[-1].id: [b"replica 0\n"],
            }
        )
        run = _get_run(run_model, logs_api)

        assert b"".join(run.logs()) == b"replica 0\n"

    def test_returns_logs_of_requested_replica(self):
        running_job = _get_job(replica_num=0, status=JobStatus.RUNNING)
        terminated_job = _get_job(replica_num=1, status=JobStatus.TERMINATED)
        run_model = _get_run_model(status=RunStatus.RUNNING, jobs=[running_job, terminated_job])
        logs_api = _LogsAPI(
            {
                running_job.job_submissions[-1].id: [b"replica 0\n"],
                terminated_job.job_submissions[-1].id: [b"replica 1\n"],
            }
        )
        run = _get_run(run_model, logs_api)

        assert b"".join(run.logs(replica_num=1)) == b"replica 1\n"


class TestRunCollectionGetRunPlan:
    def _get_run_plan(
        self, ssh_identity_file: Optional[Path] = None, ssh_key_pub: Optional[str] = None
    ) -> RunSpec:
        api_client = _PlansAPIClient()
        runs = RunCollection(api_client=api_client, project="main", client=None)

        assert (
            runs.get_run_plan(
                configuration=TaskConfiguration(commands=["echo hello"], image="ubuntu:latest"),
                ssh_identity_file=ssh_identity_file,
                ssh_key_pub=ssh_key_pub,
            )
            == "run-plan"
        )

        return api_client.runs.run_specs[0]

    def test_uses_public_key_file(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)
        (tmp_path / "id_ed25519.pub").write_text(PUBLIC_KEY)

        assert self._get_run_plan(private_key_path).ssh_key_pub == PUBLIC_KEY

    def test_generates_public_key(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)

        assert self._get_run_plan(private_key_path).ssh_key_pub == PUBLIC_KEY_NO_COMMENT

    def test_accepts_public_key(self, tmp_path: Path):
        public_key_path = tmp_path / "id_ed25519.pub"
        public_key_path.write_text(PUBLIC_KEY)

        assert self._get_run_plan(public_key_path).ssh_key_pub == PUBLIC_KEY

    def test_uses_user_key_if_no_key_given(self):
        assert self._get_run_plan().ssh_key_pub is None

    def test_uses_public_key_as_is(self):
        assert self._get_run_plan(ssh_key_pub=PUBLIC_KEY).ssh_key_pub == PUBLIC_KEY

    def test_raises_if_both_public_key_and_identity_file_given(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)

        with pytest.raises(ConfigurationError, match="mutually exclusive"):
            self._get_run_plan(ssh_identity_file=private_key_path, ssh_key_pub=PUBLIC_KEY)

    def test_raises_if_key_does_not_exist(self, tmp_path: Path):
        with pytest.raises(ConfigurationError, match="Unable to read the SSH key"):
            self._get_run_plan(tmp_path / "id_ed25519")

    def test_raises_if_key_type_is_not_supported(self, tmp_path: Path):
        key_path = tmp_path / "id_ed25519"
        key_path.write_text("garbage")

        with pytest.raises(ConfigurationError, match="Unsupported or invalid SSH key"):
            self._get_run_plan(key_path)
