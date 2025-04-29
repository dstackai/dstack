from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from dstack._internal.core.models.volumes import VolumeStatus
from dstack._internal.server.services.volumes import _get_volume_cost
from dstack._internal.server.testing.common import get_volume, get_volume_provisioning_data


class TestGetVolumeCost:
    def test_returns_0_when_no_provisioning_data(self):
        volume = get_volume(provisioning_data=None)
        assert _get_volume_cost(volume) == 0.0

    def test_returns_0_when_no_price(self):
        volume = get_volume(
            provisioning_data=get_volume_provisioning_data(price=None),
        )
        assert _get_volume_cost(volume) == 0.0

    @freeze_time(datetime(2025, 1, 31, 0, 0, tzinfo=timezone.utc))
    def test_calculates_active_volume_cost(self):
        volume = get_volume(
            status=VolumeStatus.ACTIVE,
            deleted=False,
            provisioning_data=get_volume_provisioning_data(price=30),
            created_at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        )
        assert _get_volume_cost(volume) == pytest.approx(30.0)

    @freeze_time(datetime(2025, 1, 31, 0, 0, tzinfo=timezone.utc))
    def test_calculates_finished_volume_cost(self):
        volume = get_volume(
            provisioning_data=get_volume_provisioning_data(price=30),
            created_at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            deleted=True,
            deleted_at=datetime(2025, 1, 16, 0, 0, tzinfo=timezone.utc),  # 15 days later
        )
        # Cost should be for 15 days out of a 30-day pricing period
        assert _get_volume_cost(volume) == pytest.approx(15.0)

    @freeze_time(datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc))
    def test_calculates_zero_cost_for_zero_duration_active(self):
        volume = get_volume(
            status=VolumeStatus.ACTIVE,
            deleted=False,
            provisioning_data=get_volume_provisioning_data(price=30),
            created_at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),  # Same as frozen time
        )
        assert _get_volume_cost(volume) == 0.0

    def test_calculates_zero_cost_for_zero_duration_finished(self):
        finished_time = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        volume = get_volume(
            status=VolumeStatus.FAILED,
            deleted=False,  # Can be failed without being deleted
            provisioning_data=get_volume_provisioning_data(price=30),
            created_at=finished_time,
            last_processed_at=finished_time,
        )
        assert _get_volume_cost(volume) == 0.0
