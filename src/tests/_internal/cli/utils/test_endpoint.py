from datetime import datetime, timezone
from uuid import uuid4

from dstack._internal.cli.utils.endpoint import filter_endpoints_for_listing, get_endpoints_table
from dstack._internal.core.models.endpoints import (
    Endpoint,
    EndpointConfiguration,
    EndpointStatus,
)


def _get_endpoint(
    name: str = "qwen-endpoint",
    status: EndpointStatus = EndpointStatus.FAILED,
    created_at: datetime | None = None,
) -> Endpoint:
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    return Endpoint(
        id=uuid4(),
        name=name,
        project_name="main",
        user="test-user",
        configuration=EndpointConfiguration(name=name, model="Qwen/Qwen3-0.6B"),
        created_at=created_at,
        last_processed_at=created_at,
        status=status,
        status_message="No matching endpoint presets found.",
        deleted=False,
    )


class TestGetEndpointsTable:
    def test_default_table_does_not_show_status_message(self):
        table = get_endpoints_table([_get_endpoint()])

        assert "ERROR" not in [column.header for column in table.columns]

    def test_verbose_table_shows_status_message(self):
        table = get_endpoints_table([_get_endpoint()], verbose=True)

        assert "ERROR" in [column.header for column in table.columns]

    def test_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint()])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[indian_red1]failed[/]"]

    def test_running_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status=EndpointStatus.RUNNING)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[bold sea_green3]running[/]"]

    def test_agenting_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status=EndpointStatus.AGENTING)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[bold medium_purple1]agenting[/]"]


class TestFilterEndpointsForListing:
    def test_default_shows_unfinished_and_latest_finished(self):
        endpoints = [
            _get_endpoint(
                name="failed-old",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="running",
                status=EndpointStatus.RUNNING,
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="failed-new",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="agenting",
                status=EndpointStatus.AGENTING,
                created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints)

        assert [endpoint.name for endpoint in filtered] == [
            "agenting",
            "failed-new",
            "running",
        ]

    def test_default_shows_latest_finished_when_none_are_unfinished(self):
        endpoints = [
            _get_endpoint(
                name="failed-old",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="failed-new",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints)

        assert [endpoint.name for endpoint in filtered] == ["failed-new"]

    def test_watch_default_shows_only_unfinished(self):
        endpoints = [
            _get_endpoint(
                name="failed-new",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="agenting",
                status=EndpointStatus.AGENTING,
                created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints, include_latest_finished=False)

        assert [endpoint.name for endpoint in filtered] == ["agenting"]

    def test_all_shows_all_sorted_newest_first(self):
        endpoints = [
            _get_endpoint(
                name="older",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="newer",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints, show_all=True)

        assert [endpoint.name for endpoint in filtered] == ["newer", "older"]

    def test_last_implies_all(self):
        endpoints = [
            _get_endpoint(
                name="oldest",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="middle",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="newest",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints, limit=2)

        assert [endpoint.name for endpoint in filtered] == ["newest", "middle"]
