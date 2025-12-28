from typing import List, Optional, Protocol
from uuid import UUID

from dstack._internal.core.errors import ServerClientError
from dstack._internal.core.models.logs import (
    JobSubmissionLogs,
    LogEvent,
    LogEventSource,
    LogProducer,
)
from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.base import (
    LogStorage,
    LogStorageError,
    unix_time_ms_to_datetime,
)
from dstack._internal.utils.common import batched
from dstack._internal.utils.logging import get_logger

logger = get_logger(__name__)


ELASTICSEARCH_AVAILABLE = True
try:
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import ApiError, TransportError
except ImportError:
    ELASTICSEARCH_AVAILABLE = False
else:
    ElasticsearchError: tuple = (ApiError, TransportError)  # type: ignore[misc]

    class ElasticsearchReader:
        """Reads logs from Elasticsearch or OpenSearch."""

        def __init__(
            self,
            host: str,
            index: str,
            api_key: Optional[str] = None,
        ) -> None:
            if api_key:
                self._client = Elasticsearch(hosts=[host], api_key=api_key)
            else:
                self._client = Elasticsearch(hosts=[host])
            self._index = index
            # Verify connection
            try:
                self._client.info()
            except ElasticsearchError as e:
                raise LogStorageError(f"Failed to connect to Elasticsearch/OpenSearch: {e}") from e

        def read(
            self,
            stream_name: str,
            request: PollLogsRequest,
        ) -> JobSubmissionLogs:
            sort_order = "desc" if request.descending else "asc"

            query: dict = {
                "bool": {
                    "must": [
                        {"term": {"stream.keyword": stream_name}},
                    ]
                }
            }

            if request.start_time:
                query["bool"].setdefault("filter", []).append(
                    {"range": {"@timestamp": {"gt": request.start_time.isoformat()}}}
                )
            if request.end_time:
                query["bool"].setdefault("filter", []).append(
                    {"range": {"@timestamp": {"lt": request.end_time.isoformat()}}}
                )

            search_params: dict = {
                "index": self._index,
                "query": query,
                "sort": [
                    {"@timestamp": {"order": sort_order}},
                    {"_id": {"order": sort_order}},
                ],
                "size": request.limit,
            }

            if request.next_token:
                parts = request.next_token.split(":", 1)
                if len(parts) != 2 or not parts[0] or not parts[1]:
                    raise ServerClientError(
                        f"Invalid next_token: {request.next_token}. "
                        "Must be in format 'timestamp:document_id'."
                    )
                search_params["search_after"] = [parts[0], parts[1]]

            try:
                response = self._client.search(**search_params)
            except ElasticsearchError as e:
                logger.error("Elasticsearch/OpenSearch search error: %s", e)
                raise LogStorageError(f"Elasticsearch/OpenSearch error: {e}") from e

            hits = response.get("hits", {}).get("hits", [])
            logs = []
            last_sort_values = None

            for hit in hits:
                source = hit.get("_source", {})
                timestamp_str = source.get("@timestamp")
                message = source.get("message", "")

                if timestamp_str:
                    from datetime import datetime

                    try:
                        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                else:
                    continue

                logs.append(
                    LogEvent(
                        timestamp=timestamp,
                        log_source=LogEventSource.STDOUT,
                        message=message,
                    )
                )

                sort_values = hit.get("sort")
                if sort_values and len(sort_values) >= 2:
                    last_sort_values = sort_values

            next_token = None
            if len(logs) == request.limit and last_sort_values is not None:
                next_token = f"{last_sort_values[0]}:{last_sort_values[1]}"

            return JobSubmissionLogs(
                logs=logs,
                next_token=next_token,
            )

        def close(self) -> None:
            self._client.close()


FLUENTBIT_AVAILABLE = True
try:
    import httpx
    from fluent import sender as fluent_sender
except ImportError:
    FLUENTBIT_AVAILABLE = False
else:

    class FluentBitWriter(Protocol):
        def write(self, tag: str, records: List[dict]) -> None: ...
        def close(self) -> None: ...

    class LogReader(Protocol):
        def read(self, stream_name: str, request: PollLogsRequest) -> JobSubmissionLogs: ...
        def close(self) -> None: ...

    class HTTPFluentBitWriter:
        """Writes logs to Fluent-bit via HTTP POST."""

        def __init__(self, host: str, port: int) -> None:
            self._endpoint = f"http://{host}:{port}"
            self._client = httpx.Client(timeout=30.0)

        def write(self, tag: str, records: List[dict]) -> None:
            for record in records:
                try:
                    response = self._client.post(
                        f"{self._endpoint}/{tag}",
                        json=record,
                        headers={"Content-Type": "application/json"},
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    logger.error(
                        "Fluent-bit HTTP request failed with status %d: %s",
                        e.response.status_code,
                        e.response.text,
                    )
                    raise LogStorageError(
                        f"Fluent-bit HTTP error: status {e.response.status_code}"
                    ) from e
                except httpx.HTTPError as e:
                    logger.error("Failed to write log to Fluent-bit via HTTP: %s", e)
                    raise LogStorageError(f"Fluent-bit HTTP error: {e}") from e

        def close(self) -> None:
            self._client.close()

    class ForwardFluentBitWriter:
        """Writes logs to Fluent-bit using Forward protocol."""

        def __init__(self, host: str, port: int, tag_prefix: str) -> None:
            self._sender = fluent_sender.FluentSender(tag_prefix, host=host, port=port)
            self._tag_prefix = tag_prefix

        def write(self, tag: str, records: List[dict]) -> None:
            for record in records:
                if not self._sender.emit(tag, record):
                    error = self._sender.last_error
                    logger.error("Failed to write log to Fluent-bit via Forward: %s", error)
                    self._sender.clear_last_error()
                    raise LogStorageError(f"Fluent-bit Forward error: {error}")

        def close(self) -> None:
            self._sender.close()

    class NullLogReader:
        """
        Null reader for ship-only mode (no Elasticsearch/OpenSearch configured).

        Returns empty logs. Useful when logs are shipped to an external system
        that is accessed directly rather than through dstack.
        """

        def read(self, stream_name: str, request: PollLogsRequest) -> JobSubmissionLogs:
            return JobSubmissionLogs(logs=[], next_token=None)

        def close(self) -> None:
            pass

    class FluentBitLogStorage(LogStorage):
        """
        Log storage using Fluent-bit for writing and optionally Elasticsearch/OpenSearch for reading.

        Supports two modes:
        - Full mode: Writes to Fluent-bit and reads from Elasticsearch/OpenSearch
        - Ship-only mode: Writes to Fluent-bit only (no reading, returns empty logs)
        """

        MAX_BATCH_SIZE = 100

        def __init__(
            self,
            host: str,
            port: int,
            protocol: str,
            tag_prefix: str,
            es_host: Optional[str] = None,
            es_index: str = "dstack-logs",
            es_api_key: Optional[str] = None,
        ) -> None:
            self._tag_prefix = tag_prefix

            if protocol == "http":
                self._writer: FluentBitWriter = HTTPFluentBitWriter(host=host, port=port)
            elif protocol == "forward":
                self._writer = ForwardFluentBitWriter(host=host, port=port, tag_prefix=tag_prefix)
            else:
                raise LogStorageError(f"Unsupported Fluent-bit protocol: {protocol}")

            self._reader: LogReader
            if es_host:
                if not ELASTICSEARCH_AVAILABLE:
                    raise LogStorageError(
                        "Elasticsearch/OpenSearch host configured but elasticsearch package "
                        "is not installed. Install with: pip install elasticsearch"
                    )
                self._reader = ElasticsearchReader(
                    host=es_host,
                    index=es_index,
                    api_key=es_api_key,
                )
                logger.debug(
                    "Fluent-bit log storage initialized with Elasticsearch/OpenSearch reader"
                )
            else:
                self._reader = NullLogReader()
                logger.info(
                    "Fluent-bit log storage initialized in ship-only mode "
                    "(no Elasticsearch/OpenSearch configured for reading)"
                )

        def poll_logs(self, project: ProjectModel, request: PollLogsRequest) -> JobSubmissionLogs:
            producer = LogProducer.RUNNER if request.diagnose else LogProducer.JOB
            stream_name = self._get_stream_name(
                project_name=project.name,
                run_name=request.run_name,
                job_submission_id=request.job_submission_id,
                producer=producer,
            )
            return self._reader.read(stream_name=stream_name, request=request)

        def write_logs(
            self,
            project: ProjectModel,
            run_name: str,
            job_submission_id: UUID,
            runner_logs: List[RunnerLogEvent],
            job_logs: List[RunnerLogEvent],
        ) -> None:
            producers_with_logs = [(LogProducer.RUNNER, runner_logs), (LogProducer.JOB, job_logs)]
            for producer, producer_logs in producers_with_logs:
                if not producer_logs:
                    continue
                stream_name = self._get_stream_name(
                    project_name=project.name,
                    run_name=run_name,
                    job_submission_id=job_submission_id,
                    producer=producer,
                )
                self._write_logs_to_stream(stream_name=stream_name, logs=producer_logs)

        def _write_logs_to_stream(self, stream_name: str, logs: List[RunnerLogEvent]) -> None:
            for batch in batched(logs, self.MAX_BATCH_SIZE):
                records = []
                for log in batch:
                    message = log.message.decode(errors="replace")
                    timestamp = unix_time_ms_to_datetime(log.timestamp)
                    records.append(
                        {
                            "message": message,
                            "@timestamp": timestamp.isoformat(),
                            "stream": stream_name,
                        }
                    )
                self._writer.write(tag=stream_name, records=records)

        def close(self) -> None:
            try:
                self._writer.close()
            finally:
                self._reader.close()

        def _get_stream_name(
            self, project_name: str, run_name: str, job_submission_id: UUID, producer: LogProducer
        ) -> str:
            return f"{project_name}/{run_name}/{job_submission_id}/{producer.value}"
