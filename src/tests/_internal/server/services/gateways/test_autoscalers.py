import datetime
from typing import Dict
from unittest.mock import patch

import pytest

from dstack._internal.server.services.gateways.autoscalers import ReplicaInfo, RPSAutoscaler
from dstack._internal.server.services.gateways.client import Stat


@pytest.fixture
def rps_scaler():
    return RPSAutoscaler(0, 5, 10, 5 * 60, 10 * 60)


@pytest.fixture
def time():
    dt = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
    with patch("dstack._internal.utils.common.get_current_datetime") as mock:
        mock.return_value = dt
        yield dt


def stats(rps: float) -> Dict[int, Stat]:
    return {60: Stat(requests=int(rps * 60), request_time=0.1)}


def replica(time: datetime.datetime, active: bool = True, timestamp: int = -3600) -> ReplicaInfo:
    return ReplicaInfo(
        active=active,
        timestamp=time + datetime.timedelta(seconds=timestamp),
    )


class TestRPSAutoscaler:
    def test_do_not_scale(self, rps_scaler, time):
        assert rps_scaler.scale([replica(time, active=True)], stats(rps=10)) == 0

    def test_scale_up(self, rps_scaler, time):
        assert rps_scaler.scale([replica(time, active=True)], stats(rps=20)) == 1

    def test_scale_up_high_load(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    replica(time, active=True),
                    replica(time, active=True),
                ],
                stats(rps=50),
            )
            == 3
        )

    def test_scale_up_replicas_limit(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    replica(time, active=True),
                    replica(time, active=True),
                ],
                stats(rps=1000),
            )
            == 3
        )

    def test_scale_down(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [replica(time, active=True), replica(time, active=True)], stats(rps=5)
            )
            == -1
        )

    def test_scale_up_delayed_running(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    # submitted 1 minute ago, but the delay is 5 minutes
                    replica(time, active=True, timestamp=-60),
                ],
                stats(rps=20),
            )
            == 0
        )

    def test_scale_up_delayed_terminated(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    replica(time, active=True),
                    # terminated 1 minute ago, but the delay is 5 minutes
                    replica(time, active=False, timestamp=-60),
                ],
                stats(rps=20),
            )
            == 0
        )

    def test_scale_down_delayed(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    replica(time, active=True),
                    # submitted 5 minutes ago, but the delay is 10 minutes
                    replica(time, active=True, timestamp=-5 * 60),
                ],
                stats(rps=5),
            )
            == 0
        )

    def test_scale_from_zero_immediately(self, rps_scaler, time):
        assert rps_scaler.scale([], stats(rps=5)) == 1

    def test_scale_from_zero_immediately_terminated(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    # terminated 1 minute ago, but there are requests
                    replica(time, active=False, timestamp=-60),
                ],
                stats(rps=5),
            )
            == 1
        )

    def test_scale_to_zero(self, rps_scaler, time):
        assert (
            rps_scaler.scale(
                [
                    replica(time, active=True),
                    replica(time, active=True),
                ],
                stats(rps=0),
            )
            == -2
        )
