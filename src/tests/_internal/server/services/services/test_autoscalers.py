import datetime
from unittest.mock import patch

import pytest

from dstack._internal.proxy.gateway.schemas.stats import PerWindowStats, Stat
from dstack._internal.server.services.services.autoscalers import BaseServiceScaler, RPSAutoscaler


@pytest.fixture
def rps_scaler():
    return RPSAutoscaler(0, 5, 10, 5 * 60, 10 * 60)


@pytest.fixture
def time():
    dt = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    with patch("dstack._internal.utils.common.get_current_datetime") as mock:
        mock.return_value = dt
        yield dt


def stats(rps: float) -> PerWindowStats:
    return {60: Stat(requests=int(rps * 60), request_time=0.1)}


class TestRPSAutoscaler:
    def test_do_not_scale(self, rps_scaler: BaseServiceScaler, time: datetime.datetime) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=1,
                stats=stats(rps=10),
                last_scaled_at=time - datetime.timedelta(seconds=3600),
            )
            == 1
        )

    def test_scale_up(self, rps_scaler: BaseServiceScaler, time: datetime.datetime) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=1,
                stats=stats(rps=20),
                last_scaled_at=time - datetime.timedelta(seconds=3600),
            )
            == 2
        )

    def test_scale_up_high_load(
        self, rps_scaler: BaseServiceScaler, time: datetime.datetime
    ) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=2,
                stats=stats(rps=50),
                last_scaled_at=time - datetime.timedelta(seconds=3600),
            )
            == 5
        )

    def test_scale_up_replicas_limit(
        self, rps_scaler: BaseServiceScaler, time: datetime.datetime
    ) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=2,
                stats=stats(rps=1000),
                last_scaled_at=time - datetime.timedelta(seconds=3600),
            )
            == 5
        )

    def test_scale_down(self, rps_scaler: BaseServiceScaler, time: datetime.datetime) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=2,
                stats=stats(rps=5),
                last_scaled_at=time - datetime.timedelta(seconds=3600),
            )
            == 1
        )

    def test_scale_up_delayed(
        self, rps_scaler: BaseServiceScaler, time: datetime.datetime
    ) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=1,
                stats=stats(rps=20),
                # last scaled 1 minute ago, but the delay is 5 minutes
                last_scaled_at=time - datetime.timedelta(seconds=60),
            )
            == 1
        )

    def test_scale_down_delayed(
        self, rps_scaler: BaseServiceScaler, time: datetime.datetime
    ) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=2,
                stats=stats(rps=5),
                # last scaled 5 minutes ago, but the delay is 10 minutes
                last_scaled_at=time - datetime.timedelta(seconds=5 * 60),
            )
            == 2
        )

    def test_scale_from_zero_first_time(
        self, rps_scaler: BaseServiceScaler, time: datetime.datetime
    ) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=0,
                stats=stats(rps=5),
                last_scaled_at=None,
            )
            == 1
        )

    def test_scale_from_zero_immediately(
        self, rps_scaler: BaseServiceScaler, time: datetime.datetime
    ) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=0,
                stats=stats(rps=5),
                # last scaled 1 second ago, but there are requests
                last_scaled_at=time - datetime.timedelta(seconds=1),
            )
            == 1
        )

    def test_scale_to_zero(self, rps_scaler: BaseServiceScaler, time: datetime.datetime) -> None:
        assert (
            rps_scaler.get_desired_count(
                current_desired_count=2,
                stats=stats(rps=0),
                last_scaled_at=time - datetime.timedelta(seconds=3600),
            )
            == 0
        )
