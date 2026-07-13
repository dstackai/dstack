from unittest.mock import Mock, patch

import pytest
from oci.exceptions import ClientError

from dstack._internal.core.backends.oci.configurator import OCIConfigurator
from dstack._internal.core.backends.oci.models import (
    OCIBackendConfigWithCreds,
    OCIClientCreds,
)
from dstack._internal.core.errors import (
    BackendInvalidCredentialsError,
    ServerClientError,
)


class TestOCIConfigurator:
    def test_validate_config_valid(self):
        config = OCIBackendConfigWithCreds(
            creds=OCIClientCreds(
                user="valid_user",
                tenancy="valid_tenancy",
                key_content="valid_key",
                key_file=None,
                pass_phrase=None,
                fingerprint="valid_fingerprint",
                region="us-ashburn-1",
            ),
            regions=["us-ashburn-1"],
        )
        with patch(
            "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
        ) as regions_mock:
            regions_mock.return_value = Mock(names=["us-ashburn-1"])
            OCIConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_invalid_creds(self):
        config = OCIBackendConfigWithCreds(
            creds=OCIClientCreds(
                user="invalid_user",
                tenancy="invalid_tenancy",
                key_content="invalid_key",
                key_file=None,
                pass_phrase=None,
                fingerprint="invalid_fingerprint",
                region="us-ashburn-1",
            ),
            regions=["us-ashburn-1"],
        )
        with (
            patch(
                "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
            ) as regions_mock,
            pytest.raises(BackendInvalidCredentialsError) as exc_info,
        ):
            regions_mock.side_effect = ClientError("Invalid credentials")
            OCIConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["creds"]]

    def test_validate_config_nsg_region_typo(self):
        config = OCIBackendConfigWithCreds(
            creds=OCIClientCreds(
                user="valid_user",
                tenancy="valid_tenancy",
                key_content="valid_key",
                key_file=None,
                pass_phrase=None,
                fingerprint="valid_fingerprint",
                region="us-ashburn-1",
            ),
            regions=["us-ashburn-1"],
            network_security_group_ids={"us-ashburn-typo": "ocid1.nsg.oc1..custom"},
        )
        with (
            patch(
                "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
            ) as regions_mock,
            pytest.raises(ServerClientError) as exc_info,
        ):
            regions_mock.return_value = Mock(names=["us-ashburn-1"])
            OCIConfigurator().validate_config(config, default_creds_enabled=True)
        assert exc_info.value.fields == [["network_security_group_ids"]]

    def test_validate_config_nsg_region_valid(self):
        config = OCIBackendConfigWithCreds(
            creds=OCIClientCreds(
                user="valid_user",
                tenancy="valid_tenancy",
                key_content="valid_key",
                key_file=None,
                pass_phrase=None,
                fingerprint="valid_fingerprint",
                region="us-ashburn-1",
            ),
            regions=["us-ashburn-1"],
            network_security_group_ids={"us-ashburn-1": "ocid1.nsg.oc1..custom"},
        )
        with patch(
            "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
        ) as regions_mock:
            regions_mock.return_value = Mock(names=["us-ashburn-1"])
            OCIConfigurator().validate_config(config, default_creds_enabled=True)

    def test_validate_config_nsg_no_regions_skips_check(self):
        config = OCIBackendConfigWithCreds(
            creds=OCIClientCreds(
                user="valid_user",
                tenancy="valid_tenancy",
                key_content="valid_key",
                key_file=None,
                pass_phrase=None,
                fingerprint="valid_fingerprint",
                region="us-ashburn-1",
            ),
            network_security_group_ids={"us-ashburn-1": "ocid1.nsg.oc1..custom"},
        )
        with patch(
            "dstack._internal.core.backends.oci.configurator.get_subscribed_regions"
        ) as regions_mock:
            regions_mock.return_value = Mock(names=["us-ashburn-1"])
            OCIConfigurator().validate_config(config, default_creds_enabled=True)
