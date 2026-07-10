from datetime import datetime, timezone
from uuid import uuid4

from dstack._internal.cli.utils.endpoint import (
    filter_endpoints_for_listing,
    get_endpoint_table,
    get_endpoints_table,
)
from dstack._internal.core.models.endpoints import (
    Endpoint,
    EndpointConfiguration,
    EndpointStatus,
)


def _get_endpoint(
    name: str = "qwen-endpoint",
    status: EndpointStatus = EndpointStatus.FAILED,
    status_message: str | None = "No matching endpoint presets found.",
    created_at: datetime | None = None,
    model_repo: str | None = None,
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
        status_message=status_message,
        model_repo=model_repo,
    )


class TestGetEndpointsTable:
    def test_default_table_does_not_show_status_message(self):
        table = get_endpoints_table([_get_endpoint()])

        assert "ERROR" not in [column.header for column in table.columns]

    def test_default_table_shows_preset_policy_not_service_run(self):
        table = get_endpoints_table([_get_endpoint()])

        headers = [column.header for column in table.columns]
        assert "POLICY" in headers
        assert "SERVICE RUN" not in headers

    def test_verbose_table_shows_status_message(self):
        table = get_endpoints_table([_get_endpoint()], verbose=True)

        assert "ERROR" in [column.header for column in table.columns]
        assert "SERVICE RUN" in [column.header for column in table.columns]

    def test_failed_status_without_reason_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status_message=None)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[indian_red1]failed[/]"]

    def test_no_preset_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint()])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[indian_red1]no preset[/]"]

    def test_no_agent_status_is_colored(self):
        table = get_endpoints_table(
            [
                _get_endpoint(
                    status_message=(
                        "No matching endpoint presets found. Creating a preset requires "
                        "the server agent, but DSTACK_AGENT_ANTHROPIC_API_KEY is not set."
                    )
                )
            ]
        )

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[indian_red1]no agent[/]"]

    def test_no_offers_status_is_colored(self):
        table = get_endpoints_table(
            [
                _get_endpoint(
                    status_message=(
                        "No dstack service could be deployed because max_price matches "
                        "ZERO offers."
                    )
                )
            ]
        )

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[gold1]no offers[/]"]

    def test_agent_failed_status_is_colored(self):
        table = get_endpoints_table(
            [_get_endpoint(status_message="Server agent process exited without a final report")]
        )

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[indian_red1]agent failed[/]"]

    def test_running_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status=EndpointStatus.RUNNING)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[bold sea_green3]running[/]"]

    def test_prototyping_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status=EndpointStatus.PROTOTYPING)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[bold medium_purple1]prototyping[/]"]

    def test_stopping_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status=EndpointStatus.STOPPING)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[bold deep_sky_blue1]stopping[/]"]

    def test_stopped_status_is_colored(self):
        table = get_endpoints_table([_get_endpoint(status=EndpointStatus.STOPPED)])

        status_column = next(column for column in table.columns if column.header == "STATUS")
        assert status_column._cells == ["[grey62]stopped[/]"]

    def test_shows_repo_row_when_repo_differs_from_model(self):
        table = get_endpoints_table([_get_endpoint(model_repo="groxaxo/Qwen3-0.6B-GPTQ-4Bit")])

        model_column = next(column for column in table.columns if column.header == "MODEL")
        assert model_column._cells == [
            "Qwen/Qwen3-0.6B",
            "   repo=groxaxo/Qwen3-0.6B-GPTQ-4Bit",
        ]


class TestGetEndpointTable:
    def test_shows_endpoint_details(self):
        endpoint = _get_endpoint(
            status_message="No matching endpoint presets found.",
            model_repo="groxaxo/Qwen3-0.6B-GPTQ-4Bit",
        )

        table = get_endpoint_table(endpoint, format_date=lambda _: "now")

        assert table.columns[0]._cells == [
            "[bold]Project[/bold]",
            "[bold]User[/bold]",
            "[bold]Endpoint[/bold]",
            "[bold]Model[/bold]",
            "[bold]Repo[/bold]",
            "[bold]Status[/bold]",
            "[bold]Preset policy[/bold]",
            "[bold]Service run[/bold]",
            "[bold]URL[/bold]",
            "[bold]Created[/bold]",
            "[bold]Error[/bold]",
        ]
        assert table.columns[1]._cells == [
            "main",
            "test-user",
            "qwen-endpoint",
            "Qwen/Qwen3-0.6B",
            "groxaxo/Qwen3-0.6B-GPTQ-4Bit",
            "[indian_red1]no preset[/]",
            "reuse-or-create",
            "-",
            "-",
            "now",
            "No matching endpoint presets found.",
        ]


class TestFilterEndpointsForListing:
    def test_default_shows_unfinished_only_when_present(self):
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
                name="prototyping",
                status=EndpointStatus.PROTOTYPING,
                created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints)

        assert [endpoint.name for endpoint in filtered] == [
            "prototyping",
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

    def test_default_hides_latest_finished_when_unfinished_exist(self):
        endpoints = [
            _get_endpoint(
                name="failed-new",
                status=EndpointStatus.FAILED,
                created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
            ),
            _get_endpoint(
                name="prototyping",
                status=EndpointStatus.PROTOTYPING,
                created_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
            ),
        ]

        filtered = filter_endpoints_for_listing(endpoints)

        assert [endpoint.name for endpoint in filtered] == ["prototyping"]

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
