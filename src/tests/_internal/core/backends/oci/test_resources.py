import pytest

from dstack._internal.core.backends.oci.resources import ShapesQuota


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
