import logging
from unittest.mock import Mock

import botocore.exceptions
import pytest

from dstack._internal.core.backends.aws.compute import _get_regions_to_quotas


def _session_raising(error_code: str) -> Mock:
    client = Mock()
    client.get_service_quota.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": error_code, "Message": ""}}, "GetServiceQuota"
    )
    session = Mock()
    session.client.return_value = client
    return session


class TestGetRegionsToQuotas:
    def test_returns_quotas(self):
        client = Mock()
        client.get_service_quota.return_value = {"Quota": {"Value": 8}}
        session = Mock()
        session.client.return_value = client

        assert _get_regions_to_quotas(session=session, regions=["eu-west-1"]) == {
            "eu-west-1": {
                "Standard/OnDemand": 8,
                "P/OnDemand": 8,
                "G/OnDemand": 8,
            }
        }

    @pytest.mark.parametrize("error_code", ["408", "UnrecognizedClientException"])
    def test_expected_errors_are_not_reported(self, error_code: str, caplog):
        with caplog.at_level(logging.WARNING):
            regions_to_quotas = _get_regions_to_quotas(
                session=_session_raising(error_code), regions=["eu-west-1"]
            )

        assert regions_to_quotas == {"eu-west-1": {}}
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_code in caplog.text

    def test_unexpected_error_is_reported(self, caplog):
        with caplog.at_level(logging.WARNING):
            regions_to_quotas = _get_regions_to_quotas(
                session=_session_raising("NoSuchResourceException"), regions=["eu-west-1"]
            )

        assert regions_to_quotas == {"eu-west-1": {}}
        assert [r for r in caplog.records if r.levelno >= logging.ERROR]
