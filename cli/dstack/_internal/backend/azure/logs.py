import json
from datetime import datetime
from typing import Dict, Generator, Optional

from azure.core.credentials import TokenCredential
from azure.mgmt.loganalytics import LogAnalyticsManagementClient
from azure.monitor.query import LogsQueryClient, LogsTable

from dstack._internal.backend.azure.utils import DSTACK_LOGS_TABLE_NAME, get_logs_workspace_name
from dstack._internal.backend.base import jobs as base_jobs
from dstack._internal.backend.base.logs import Logging, fix_log_event_urls
from dstack._internal.backend.base.storage import Storage
from dstack._internal.core.log_event import LogEvent
from dstack._internal.utils.common import get_current_datetime


class AzureLogging(Logging):
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
        repo_id: str,
        run_name: str,
        start_time: datetime,
        end_time: Optional[datetime],
        descending: bool,
        diagnose: bool,
    ) -> Generator[LogEvent, None, None]:
        jobs = base_jobs.list_jobs(storage, repo_id, run_name)
        jobs_map = {j.job_id: j for j in jobs}
        if diagnose:
            runner_id = jobs[0].runner_id
            log_name = _get_runnners_log_name(self.resource_group, runner_id)
        else:
            log_name = _get_jobs_log_name(self.resource_group, repo_id, run_name)
        logs = self._query_logs(
            log_name=log_name, start_time=start_time, end_time=end_time, descending=descending
        )
        for log_entry in logs:
            log_event = _log_entry_to_log_event(log_entry)
            if not diagnose:
                log_event = fix_log_event_urls(log_event, jobs_map)
            yield log_event

    def _get_workspace_id(self) -> str:
        workspace = self.log_analytics_client.workspaces.get(
            resource_group_name=self.resource_group,
            workspace_name=self.workspace_name,
        )
        return workspace.customer_id

    def _query_logs(
        self,
        log_name: str,
        start_time: datetime,
        end_time: Optional[datetime],
        descending: bool,
    ) -> Generator[Dict, None, None]:
        if end_time is None:
            end_time = get_current_datetime()
        order = "desc" if descending else "asc"
        response = self.logs_query_client.query_workspace(
            workspace_id=self.workspace_id,
            query=f'{self.logs_table} | where LogName == "{log_name}" | order by TimeGenerated {order}',
            timespan=(start_time, end_time),
        )
        table = response.tables[0]
        yield from _parse_log_entries_from_table(table)


def _get_jobs_log_name(resource_group: str, repo_id: str, run_name: str):
    return f"dstack-jobs-{resource_group}-{repo_id}-{run_name}"


def _get_runnners_log_name(resource_group: str, runner_id: str):
    return f"dstack-runners-{resource_group}-{runner_id}"


def _parse_log_entries_from_table(table: LogsTable) -> Generator[Dict, None, None]:
    log_name_idx = table.columns.index("LogName")
    time_generated_idx = table.columns.index("TimeGenerated")
    json_payload_idx = table.columns.index("JsonPayload")
    event_id_idx = table.columns.index("EventID")
    for row in table.rows:
        yield {
            "EventID": row[event_id_idx],
            "LogName": row[log_name_idx],
            "TimeGenerated": row[time_generated_idx],
            "JsonPayload": row[json_payload_idx],
        }


def _log_entry_to_log_event(log_entry: Dict) -> LogEvent:
    payload = json.loads(log_entry["JsonPayload"])
    log = payload["log"]
    job_id = payload["job_id"]
    return LogEvent(
        event_id=log_entry["EventID"],
        timestamp=log_entry["TimeGenerated"].timestamp(),
        job_id=job_id,
        log_source=payload["source"],
        log_message=log,
    )
