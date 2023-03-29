import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Generator

from azure.core.credentials import TokenCredential
from azure.mgmt.loganalytics import LogAnalyticsManagementClient
from azure.monitor.query import LogsQueryClient, LogsTable

from dstack.backend.azure.utils import DSTACK_LOGS_TABLE_NAME, get_logs_workspace_name
from dstack.backend.base import jobs as base_jobs
from dstack.backend.base.logs import fix_urls
from dstack.backend.base.storage import Storage
from dstack.core.job import Job
from dstack.core.log_event import LogEvent
from dstack.core.repo import RepoAddress

POLL_LOGS_ATTEMPTS = 10
POLL_LOGS_WAIT_TIME = 2


class AzureLogging:
    def __init__(
        self,
        credential: TokenCredential,
        subscription_id: str,
        resource_group: str,
        storage_account: str,
    ):
        self.log_analytics_client = LogAnalyticsManagementClient(
            credential=credential, subscription_id=subscription_id
        )
        self.logs_query_client = LogsQueryClient(credential=credential)
        self.resource_group = resource_group
        self.logs_table = DSTACK_LOGS_TABLE_NAME
        self.workspace_name = get_logs_workspace_name(storage_account)
        self.workspace_id = self._get_workspace_id()

    def poll_logs(
        self,
        storage: Storage,
        repo_address: RepoAddress,
        run_name: str,
        start_time: int,
    ) -> Generator[LogEvent, None, None]:
        jobs = {j.job_id: j for j in base_jobs.list_jobs(storage, repo_address, run_name)}
        start_date = datetime.fromtimestamp(start_time / 1000, tz=timezone.utc)
        timespan = datetime.now(tz=timezone.utc) - start_date
        log_name = _get_run_log_name(self.resource_group, repo_address, run_name)
        found_logs = False
        for _ in range(POLL_LOGS_ATTEMPTS):
            logs = self._query_logs(log_name=log_name, timespan=timespan)
            for log_entry in logs:
                found_logs = True
                yield _log_entry_to_log_event(jobs, log_entry)
            if found_logs:
                break
            time.sleep(POLL_LOGS_WAIT_TIME)

    def _get_workspace_id(self) -> str:
        workspace = self.log_analytics_client.workspaces.get(
            resource_group_name=self.resource_group,
            workspace_name=self.workspace_name,
        )
        return workspace.customer_id

    def _query_logs(
        self,
        log_name: str,
        timespan: timedelta,
    ) -> Generator[Dict, None, None]:
        response = self.logs_query_client.query_workspace(
            workspace_id=self.workspace_id,
            query=f'{self.logs_table} | where LogName == "{log_name}" | order by TimeGenerated asc',
            timespan=timespan,
        )
        table = response.tables[0]
        yield from _parse_log_entries_from_table(table)


def _get_run_log_name(resource_group: str, repo_address: RepoAddress, run_name: str):
    return f"dstack-jobs-{resource_group}-{repo_address.path('-')}-{run_name}"


def _parse_log_entries_from_table(table: LogsTable) -> Generator[Dict, None, None]:
    log_name_idx = table.columns.index("LogName")
    time_generated_idx = table.columns.index("TimeGenerated")
    json_payload_idx = table.columns.index("JsonPayload")

    for row in table.rows:
        yield {
            "LogName": row[log_name_idx],
            "TimeGenerated": row[time_generated_idx],
            "JsonPayload": row[json_payload_idx],
        }


def _log_entry_to_log_event(jobs: Dict[str, Job], log_entry: Dict) -> LogEvent:
    payload = json.loads(log_entry["JsonPayload"])
    log = payload["log"]
    job_id = payload["job_id"]
    job = jobs[job_id]
    log = fix_urls(log.encode(), job).decode()
    return LogEvent(
        event_id="dummyid",
        timestamp=int(log_entry["TimeGenerated"].timestamp()),
        job_id=job_id,
        log_source=payload["source"],
        log_message=log,
    )
