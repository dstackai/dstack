from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.server.models import ProjectModel
from dstack._internal.server.schemas.logs import PollLogsRequest
from dstack._internal.server.schemas.runner import LogEvent as RunnerLogEvent
from dstack._internal.server.services.logs.base import LogStorageError
from dstack._internal.server.services.logs.fluentbit import (
    ELASTICSEARCH_AVAILABLE,
    FLUENTBIT_AVAILABLE,
)
from dstack._internal.server.testing.common import create_project

pytestmark = pytest.mark.skipif(not FLUENTBIT_AVAILABLE, reason="fluent-logger not installed")

# Conditionally import classes that are only defined when FLUENTBIT_AVAILABLE is True
if FLUENTBIT_AVAILABLE:
    from dstack._internal.server.services.logs.fluentbit import (
        FluentBitLogStorage,
        ForwardFluentBitWriter,
        HTTPFluentBitWriter,
        NullLogReader,
    )

    if ELASTICSEARCH_AVAILABLE:
        from dstack._internal.server.services.logs.fluentbit import ElasticsearchReader


class TestNullLogReader:
    """Tests for the NullLogReader (ship-only mode)."""

    def test_read_returns_empty_logs(self):
        reader = NullLogReader()
        request = PollLogsRequest(
            run_name="test-run",
            job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
            limit=100,
        )
        result = reader.read("test-stream", request)

        assert result.logs == []
        assert result.next_token is None

    def test_close_does_nothing(self):
        reader = NullLogReader()
        reader.close()  # Should not raise


class TestHTTPFluentBitWriter:
    """Tests for the HTTPFluentBitWriter."""

    @pytest.fixture
    def mock_httpx_client(self):
        with patch("dstack._internal.server.services.logs.fluentbit.httpx.Client") as mock:
            yield mock.return_value

    def test_init_creates_client(self, mock_httpx_client):
        writer = HTTPFluentBitWriter(host="localhost", port=8080)
        assert writer._endpoint == "http://localhost:8080"

    def test_write_posts_records(self, mock_httpx_client):
        writer = HTTPFluentBitWriter(host="localhost", port=8080)
        records = [
            {"message": "Hello", "@timestamp": "2023-10-06T10:00:00+00:00"},
            {"message": "World", "@timestamp": "2023-10-06T10:00:01+00:00"},
        ]
        writer.write(tag="test-tag", records=records)

        assert mock_httpx_client.post.call_count == 2
        mock_httpx_client.post.assert_any_call(
            "http://localhost:8080/test-tag",
            json=records[0],
            headers={"Content-Type": "application/json"},
        )
        mock_httpx_client.post.assert_any_call(
            "http://localhost:8080/test-tag",
            json=records[1],
            headers={"Content-Type": "application/json"},
        )

    def test_write_raises_on_http_error(self, mock_httpx_client):
        import httpx

        mock_httpx_client.post.side_effect = httpx.HTTPError("Connection failed")
        writer = HTTPFluentBitWriter(host="localhost", port=8080)

        with pytest.raises(LogStorageError, match="Fluent-bit HTTP error"):
            writer.write(tag="test-tag", records=[{"message": "test"}])

    def test_close_closes_client(self, mock_httpx_client):
        writer = HTTPFluentBitWriter(host="localhost", port=8080)
        writer.close()
        mock_httpx_client.close.assert_called_once()


class TestForwardFluentBitWriter:
    """Tests for the ForwardFluentBitWriter."""

    @pytest.fixture
    def mock_fluent_sender(self):
        with patch(
            "dstack._internal.server.services.logs.fluentbit.fluent_sender.FluentSender"
        ) as mock:
            mock_instance = Mock()
            mock_instance.emit.return_value = True
            mock.return_value = mock_instance
            yield mock_instance

    def test_init_creates_sender(self, mock_fluent_sender):
        with patch(
            "dstack._internal.server.services.logs.fluentbit.fluent_sender.FluentSender"
        ) as mock:
            mock.return_value = mock_fluent_sender
            ForwardFluentBitWriter(host="localhost", port=24224, tag_prefix="dstack")
            mock.assert_called_once_with("dstack", host="localhost", port=24224)

    def test_write_emits_records(self, mock_fluent_sender):
        with patch(
            "dstack._internal.server.services.logs.fluentbit.fluent_sender.FluentSender"
        ) as mock:
            mock.return_value = mock_fluent_sender
            writer = ForwardFluentBitWriter(host="localhost", port=24224, tag_prefix="dstack")

            records = [
                {"message": "Hello"},
                {"message": "World"},
            ]
            writer.write(tag="test-tag", records=records)

            assert mock_fluent_sender.emit.call_count == 2

    def test_write_raises_on_emit_failure(self, mock_fluent_sender):
        mock_fluent_sender.emit.return_value = False
        mock_fluent_sender.last_error = Exception("Connection refused")

        with patch(
            "dstack._internal.server.services.logs.fluentbit.fluent_sender.FluentSender"
        ) as mock:
            mock.return_value = mock_fluent_sender
            writer = ForwardFluentBitWriter(host="localhost", port=24224, tag_prefix="dstack")

            with pytest.raises(LogStorageError, match="Fluent-bit Forward error"):
                writer.write(tag="test-tag", records=[{"message": "test"}])

            mock_fluent_sender.clear_last_error.assert_called_once()

    def test_close_closes_sender(self, mock_fluent_sender):
        with patch(
            "dstack._internal.server.services.logs.fluentbit.fluent_sender.FluentSender"
        ) as mock:
            mock.return_value = mock_fluent_sender
            writer = ForwardFluentBitWriter(host="localhost", port=24224, tag_prefix="dstack")
            writer.close()
            mock_fluent_sender.close.assert_called_once()


class TestFluentBitLogStorage:
    """Tests for the FluentBitLogStorage."""

    @pytest_asyncio.fixture
    async def project(self, test_db, session: AsyncSession) -> ProjectModel:
        project = await create_project(session=session, name="test-proj")
        return project

    @pytest.fixture
    def mock_forward_writer(self):
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock_instance = Mock()
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_http_writer(self):
        with patch("dstack._internal.server.services.logs.fluentbit.HTTPFluentBitWriter") as mock:
            mock_instance = Mock()
            mock.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_es_reader(self):
        with patch("dstack._internal.server.services.logs.fluentbit.ElasticsearchReader") as mock:
            mock_instance = Mock()
            mock.return_value = mock_instance
            yield mock_instance

    def test_init_with_forward_protocol(self, mock_forward_writer):
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )
            mock.assert_called_once_with(host="localhost", port=24224, tag_prefix="dstack")
            assert isinstance(storage._reader, NullLogReader)

    def test_init_with_http_protocol(self, mock_http_writer):
        with patch("dstack._internal.server.services.logs.fluentbit.HTTPFluentBitWriter") as mock:
            mock.return_value = mock_http_writer
            FluentBitLogStorage(
                host="localhost",
                port=8080,
                protocol="http",
                tag_prefix="dstack",
            )
            mock.assert_called_once_with(host="localhost", port=8080)

    def test_init_with_unsupported_protocol_raises(self):
        with pytest.raises(LogStorageError, match="Unsupported Fluent-bit protocol"):
            FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="grpc",
                tag_prefix="dstack",
            )

    def test_init_ship_only_mode(self, mock_forward_writer):
        """Test initialization without Elasticsearch (ship-only mode)."""
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
                es_host=None,
            )
            assert isinstance(storage._reader, NullLogReader)

    @pytest.mark.skipif(not ELASTICSEARCH_AVAILABLE, reason="elasticsearch not installed")
    def test_init_with_elasticsearch(self, mock_forward_writer, mock_es_reader):
        """Test initialization with Elasticsearch configured."""
        with (
            patch(
                "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
            ) as writer_mock,
            patch(
                "dstack._internal.server.services.logs.fluentbit.ElasticsearchReader"
            ) as reader_mock,
        ):
            writer_mock.return_value = mock_forward_writer
            reader_mock.return_value = mock_es_reader

            FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
                es_host="http://elasticsearch:9200",
                es_index="dstack-logs",
                es_api_key="test-key",
            )
            reader_mock.assert_called_once_with(
                host="http://elasticsearch:9200",
                index="dstack-logs",
                api_key="test-key",
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_write_logs(self, test_db, project: ProjectModel, mock_forward_writer):
        """Test writing logs to Fluent-bit."""
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )

            storage.write_logs(
                project=project,
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                runner_logs=[
                    RunnerLogEvent(timestamp=1696586513234, message=b"Runner log"),
                ],
                job_logs=[
                    RunnerLogEvent(timestamp=1696586513235, message=b"Job log"),
                ],
            )

            assert mock_forward_writer.write.call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_write_logs_empty_logs_not_written(
        self, test_db, project: ProjectModel, mock_forward_writer
    ):
        """Test that empty log lists are not written."""
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )

            storage.write_logs(
                project=project,
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                runner_logs=[],
                job_logs=[],
            )

            mock_forward_writer.write.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("test_db", ["sqlite", "postgres"], indirect=True)
    async def test_poll_logs_ship_only_mode(self, test_db, project: ProjectModel):
        """Test that ship-only mode returns empty logs."""
        with patch("dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"):
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )

            request = PollLogsRequest(
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                limit=100,
            )
            result = storage.poll_logs(project, request)

            assert result.logs == []
            assert result.next_token is None

    def test_close_closes_writer_and_reader(self, mock_forward_writer):
        """Test that close() closes both writer and reader."""
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )

            storage.close()

            mock_forward_writer.close.assert_called_once()

    def test_close_closes_reader_even_if_writer_fails(self, mock_forward_writer):
        """Test that reader is closed even if writer.close() raises an exception."""
        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock_forward_writer.close.side_effect = Exception("Writer close failed")
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )
            mock_reader = Mock()
            storage._reader = mock_reader

            with pytest.raises(Exception, match="Writer close failed"):
                storage.close()

            mock_reader.close.assert_called_once()

    def test_get_stream_name(self, mock_forward_writer):
        """Test stream name generation."""
        from dstack._internal.core.models.logs import LogProducer

        with patch(
            "dstack._internal.server.services.logs.fluentbit.ForwardFluentBitWriter"
        ) as mock:
            mock.return_value = mock_forward_writer
            storage = FluentBitLogStorage(
                host="localhost",
                port=24224,
                protocol="forward",
                tag_prefix="dstack",
            )

            stream_name = storage._get_stream_name(
                project_name="my-project",
                run_name="my-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                producer=LogProducer.JOB,
            )

            assert stream_name == "my-project/my-run/1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e/job"


@pytest.mark.skipif(
    not FLUENTBIT_AVAILABLE or not ELASTICSEARCH_AVAILABLE,
    reason="fluent-logger or elasticsearch not installed",
)
class TestElasticsearchReader:
    """Tests for the ElasticsearchReader."""

    @pytest.fixture
    def mock_es_client(self):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock_instance = Mock()
            mock_instance.info.return_value = {"version": {"number": "8.0.0"}}
            mock_instance.search.return_value = {"hits": {"hits": []}}
            mock.return_value = mock_instance
            yield mock_instance

    def test_init_verifies_connection(self, mock_es_client):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
            )
            mock_es_client.info.assert_called_once()

    def test_init_with_api_key(self, mock_es_client):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
                api_key="test-api-key",
            )
            mock.assert_called_once_with(hosts=["http://localhost:9200"], api_key="test-api-key")

    def test_init_connection_error_raises(self):
        from elasticsearch.exceptions import ConnectionError as ESConnectionError

        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock_instance = Mock()
            mock_instance.info.side_effect = ESConnectionError("Connection refused")
            mock.return_value = mock_instance

            with pytest.raises(LogStorageError, match="Failed to connect"):
                ElasticsearchReader(
                    host="http://localhost:9200",
                    index="dstack-logs",
                )

    def test_read_returns_logs(self, mock_es_client):
        mock_es_client.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "@timestamp": "2023-10-06T10:01:53.234000+00:00",
                            "message": "Hello",
                            "stream": "test-stream",
                        },
                        "sort": [1696586513234],
                    },
                    {
                        "_source": {
                            "@timestamp": "2023-10-06T10:01:53.235000+00:00",
                            "message": "World",
                            "stream": "test-stream",
                        },
                        "sort": [1696586513235],
                    },
                ]
            }
        }

        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            reader = ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
            )

            request = PollLogsRequest(
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                limit=2,
            )
            result = reader.read("test-stream", request)

            assert len(result.logs) == 2
            assert result.logs[0].message == "Hello"
            assert result.logs[1].message == "World"
            assert result.next_token == "1696586513235"

    def test_read_with_time_filtering(self, mock_es_client):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            reader = ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
            )

            request = PollLogsRequest(
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                start_time=datetime(2023, 10, 6, 10, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2023, 10, 6, 11, 0, 0, tzinfo=timezone.utc),
                limit=100,
            )
            reader.read("test-stream", request)

            call_args = mock_es_client.search.call_args
            query = call_args.kwargs["query"]
            assert "filter" in query["bool"]
            assert len(query["bool"]["filter"]) == 2

    def test_read_descending_order(self, mock_es_client):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            reader = ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
            )

            request = PollLogsRequest(
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                limit=100,
                descending=True,
            )
            reader.read("test-stream", request)

            call_args = mock_es_client.search.call_args
            assert call_args.kwargs["sort"] == [{"@timestamp": {"order": "desc"}}]

    def test_read_with_next_token(self, mock_es_client):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            reader = ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
            )

            request = PollLogsRequest(
                run_name="test-run",
                job_submission_id=UUID("1b0e1b45-2f8c-4ab6-8010-a0d1a3e44e0e"),
                next_token="1696586513234",
                limit=100,
            )
            reader.read("test-stream", request)

            call_args = mock_es_client.search.call_args
            assert call_args.kwargs["search_after"] == ["1696586513234"]

    def test_close_closes_client(self, mock_es_client):
        with patch("dstack._internal.server.services.logs.fluentbit.Elasticsearch") as mock:
            mock.return_value = mock_es_client
            reader = ElasticsearchReader(
                host="http://localhost:9200",
                index="dstack-logs",
            )
            reader.close()
            mock_es_client.close.assert_called_once()
