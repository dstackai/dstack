from unittest.mock import patch

from dstack._internal.core.backends.vastai.compute import VastAICompute
from dstack._internal.core.backends.vastai.models import VastAIConfig, VastAICreds


def _config(community_cloud=None) -> VastAIConfig:
    return VastAIConfig(creds=VastAICreds(api_key="test"), community_cloud=community_cloud)


def test_vastai_compute_enables_community_cloud_by_default():
    with patch(
        "dstack._internal.core.backends.vastai.compute.VastAIProvider"
    ) as vast_provider_cls, patch(
        "dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog"
    ) as catalog_cls:
        catalog_instance = catalog_cls.return_value
        VastAICompute(_config())
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is True
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_can_enable_community_cloud():
    with patch(
        "dstack._internal.core.backends.vastai.compute.VastAIProvider"
    ) as vast_provider_cls, patch(
        "dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog"
    ) as catalog_cls:
        catalog_instance = catalog_cls.return_value
        VastAICompute(_config(community_cloud=True))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is True
        catalog_instance.add_provider.assert_called_once()


def test_vastai_compute_can_disable_community_cloud():
    with patch(
        "dstack._internal.core.backends.vastai.compute.VastAIProvider"
    ) as vast_provider_cls, patch(
        "dstack._internal.core.backends.vastai.compute.gpuhunt.Catalog"
    ) as catalog_cls:
        catalog_instance = catalog_cls.return_value
        VastAICompute(_config(community_cloud=False))
        vast_provider_cls.assert_called_once()
        assert vast_provider_cls.call_args.kwargs["community_cloud"] is False
        catalog_instance.add_provider.assert_called_once()
