import datetime

import oci
import pytest

from dstack._internal.core.backends.oci.resources import SecurityRule, ShapesQuota


class TestShapesQuota:
    SAMPLE_QUOTA = ShapesQuota(
        {
            "region-1": {
                "region-1-ad-1": {"shape.1", "shape.2"},
                "region-1-ad-2": {"shape.2", "shape.3"},
            },
            "region-2": {
                "region-2-ad-1": {"shape.1", "shape.3"},
            },
        }
    )

    @pytest.mark.parametrize(
        ("shape", "region", "is_within_quota"),
        [
            ("shape.1", "region-1", True),
            ("shape.2", "region-1", True),
            ("shape.3", "region-1", True),
            ("shape.1", "region-2", True),
            ("shape.2", "region-2", False),
            ("shape.3", "region-2", True),
            ("shape.9", "region-1", False),
            ("shape.1", "region-9", False),
        ],
    )
    def test_is_within_region_quota(self, shape: str, region: str, is_within_quota: str):
        assert is_within_quota == self.SAMPLE_QUOTA.is_within_region_quota(shape, region)

    @pytest.mark.parametrize(
        ("shape", "domain", "is_within_quota"),
        [
            ("shape.1", "region-1-ad-1", True),
            ("shape.3", "region-1-ad-1", False),
            ("shape.1", "region-1-ad-2", False),
            ("shape.3", "region-1-ad-2", True),
            ("shape.1", "region-2-ad-1", True),
            ("shape.2", "region-2-ad-1", False),
            ("shape.9", "region-1-ad1", False),
            ("shape.1", "region-9-ad-9", False),
        ],
    )
    def test_is_within_domain_quota(self, shape: str, domain: str, is_within_quota: str):
        assert is_within_quota == self.SAMPLE_QUOTA.is_within_domain_quota(shape, domain)


class TestCompareSecurityRulesAfterConversion:
    def test_equal(self) -> None:
        first = SecurityRule(
            direction=oci.core.models.SecurityRule.DIRECTION_INGRESS,
            protocol="all",
            source_type=oci.core.models.SecurityRule.SOURCE_TYPE_CIDR_BLOCK,
            source="0.0.0.0/0",
        )
        second = oci.core.models.SecurityRule(
            direction=oci.core.models.SecurityRule.DIRECTION_INGRESS,
            protocol="all",
            source_type=oci.core.models.SecurityRule.SOURCE_TYPE_CIDR_BLOCK,
            source="0.0.0.0/0",
            is_stateless=False,
            id="AAAAAA",
            time_created=datetime.datetime.now(),
        )
        assert first == SecurityRule.from_sdk_rule(second)

    def test_unequal(self) -> None:
        first = SecurityRule(
            direction=oci.core.models.SecurityRule.DIRECTION_INGRESS,
            protocol="all",
            source_type=oci.core.models.SecurityRule.SOURCE_TYPE_CIDR_BLOCK,
            source="0.0.0.0/0",
        )
        second = oci.core.models.SecurityRule(
            direction=oci.core.models.SecurityRule.DIRECTION_INGRESS,
            protocol="all",
            source_type=oci.core.models.SecurityRule.SOURCE_TYPE_CIDR_BLOCK,
            source="10.10.10.0/24",
            is_stateless=False,
            id="AAAAAA",
            time_created=datetime.datetime.now(),
        )
        assert first != SecurityRule.from_sdk_rule(second)
